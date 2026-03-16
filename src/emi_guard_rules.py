"""
EMI (Equivalent Modulo Inputs) guard rule generation from constraint graph.

This module consumes `intra_constraints` and emits C guard snippets to be
inserted before API calls in the generated v2 harness.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


_PARAM_RE = re.compile(r"^param_(\d+)$")


def _param_index(name: str) -> Optional[int]:
    m = _PARAM_RE.match(name or "")
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


class EmiGuardRules:
    def __init__(self, constraint_graph_path: Optional[Path] = None):
        self.intra_constraints: Dict[str, Any] = {}
        self.inter_edges: List[Dict[str, Any]] = []
        if constraint_graph_path and constraint_graph_path.exists():
            try:
                raw = json.loads(constraint_graph_path.read_text(encoding="utf-8"))
                intra = raw.get("intra_constraints", {})
                if isinstance(intra, dict):
                    self.intra_constraints = intra
                inter = raw.get("inter_edges", [])
                if isinstance(inter, list):
                    self.inter_edges = inter
            except Exception:
                self.intra_constraints = {}
                self.inter_edges = []

    def get_guard_for_api(
        self,
        api_name: str,
        params: List[Dict[str, Any]],
        target_lang: str = "c",
    ) -> List[str]:
        """
        Return pre-call C snippets for one API call-site.

        Implemented guards:
        - `set_by`: repair missing handle by redirecting to latest live handle of same type.
          Only break when no handle of that type exists.
        - `len_depends_on`: clamp dependent scalar length to available bytes size.
        """
        api = self.intra_constraints.get(api_name)
        if not isinstance(api, dict):
            return []

        intra_params = api.get("params", {})
        if not isinstance(intra_params, dict):
            return []

        arg_by_index: Dict[int, Dict[str, Any]] = {}
        for a in params:
            try:
                idx = int(a.get("i"))
            except Exception:
                continue
            arg_by_index[idx] = a

        snippets: List[str] = []
        is_cpp = str(target_lang).lower() in ("cpp", "c++")

        def _arg(idx: int) -> str:
            return f"arg_{idx}" if is_cpp else f"arg{idx}"

        def _has_param(idx: int) -> str:
            return f"params.has_param_{idx}()" if is_cpp else f"params->has_param_{idx}"

        def _param_size(idx: int) -> str:
            return f"params.param_{idx}().size()" if is_cpp else f"params->param_{idx}.size"

        # 1) set_by guards: require referenced handle arg to be non-NULL.
        emitted_set_by = set()
        for p_name, p_meta in intra_params.items():
            if not isinstance(p_meta, dict):
                continue
            _ = _param_index(str(p_name))  # param index not needed directly here
            set_by = p_meta.get("set_by", [])
            if not isinstance(set_by, list):
                continue
            for dep in set_by:
                dep_idx = _param_index(str(dep))
                if dep_idx is None or dep_idx in emitted_set_by:
                    continue
                dep_arg = arg_by_index.get(dep_idx)
                if not dep_arg:
                    continue
                dep_param = dep_arg.get("param") if isinstance(dep_arg.get("param"), dict) else {}
                # Only enforce handle dependency in this guard (requested behavior).
                if dep_param.get("kind") != "handle":
                    continue
                dep_type_id = int(dep_param.get("type_id", 0))
                dep_c_type = str(dep_arg.get("c_type") or "void *")
                snippets.append(
                    f"if (!allow_stale && {_arg(dep_idx)} == NULL) {{\n"
                    f"    /* Repair: redirect to latest live handle of this type */\n"
                    f"    void *_repair = handle_get_typed({dep_type_id}, 0, false, NULL);\n"
                    f"    if (_repair) {{\n"
                    f"        {_arg(dep_idx)} = ({dep_c_type})_repair;\n"
                    f"        g_hard_constraint_redirected = true;\n"
                    f"    }} else {{\n"
                    f"        break; /* type pool empty, nothing to redirect to */\n"
                    f"    }}\n"
                    f"}}"
                )
                emitted_set_by.add(dep_idx)

        # 2) len_depends_on guards: clamp scalar dependency to available bytes size.
        for p_name, p_meta in intra_params.items():
            if not isinstance(p_meta, dict):
                continue
            p_idx = _param_index(str(p_name))
            if p_idx is None:
                continue
            dep_name = str(p_meta.get("len_depends_on") or "")
            dep_idx = _param_index(dep_name)
            if dep_idx is None:
                continue

            src_arg = arg_by_index.get(p_idx)
            dep_arg = arg_by_index.get(dep_idx)
            if not src_arg or not dep_arg:
                continue

            src_param = src_arg.get("param") if isinstance(src_arg.get("param"), dict) else {}
            if src_param.get("kind") not in ("bytes", "bytes_array"):
                continue

            dep_c_type = str(dep_arg.get("c_type") or "size_t")
            snippets.append(
                f"if ({_has_param(p_idx)}) {{\n"
                f"    size_t _avail_param_{p_idx} = (size_t){_param_size(p_idx)};\n"
                f"    if ((size_t){_arg(dep_idx)} > _avail_param_{p_idx}) {{\n"
                f"        {_arg(dep_idx)} = ({dep_c_type})_avail_param_{p_idx};\n"
                f"    }}\n"
                f"}}"
            )

        return snippets

    def get_post_call_check(self, api_name: str, return_var: str) -> Optional[str]:
        """
        Return post-call C/C++ snippet for one API call-site.

        Implemented check:
        - producer-like return should be non-NULL when not explicitly in stale mode.
          (A producer-like return is inferred from intra.return metadata.)
        """
        api = self.intra_constraints.get(api_name)
        if not isinstance(api, dict):
            return None

        ret_meta = api.get("return")
        if not isinstance(ret_meta, dict):
            return None

        llvm_type = str(ret_meta.get("llvm_type") or "")
        object_type = str(ret_meta.get("object_type") or "")
        accesses = ret_meta.get("accesses", [])
        if not isinstance(accesses, list):
            accesses = []
        access_set = {str(x) for x in accesses}

        producer_like = ("create" in access_set) or bool(object_type)
        pointer_like = llvm_type.endswith("*") or llvm_type.startswith("%struct.") or bool(object_type)
        if not (producer_like and pointer_like):
            return None

        return (
            f"if (!allow_stale && {return_var} == NULL) {{\n"
            f"    /* Post-call guard: producer-like API returned NULL */\n"
            f"    g_hard_constraint_redirected = true;\n"
            f"    break;\n"
            f"}}"
        )
