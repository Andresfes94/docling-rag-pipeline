from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TableStructureOptions,
    VlmPipelineOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption


def load_profiles(path: str | Path = "profiles.yaml") -> dict[str, dict]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Profiles file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data.get("profiles", {})


def list_profiles(path: str | Path = "profiles.yaml") -> list[dict]:
    profiles = load_profiles(path)
    return [
        {"name": name, "description": p.get("description", ""), "pipeline": p.get("pipeline", "standard")}
        for name, p in profiles.items()
    ]


def _build_pipeline_options(profile: dict) -> PdfPipelineOptions | VlmPipelineOptions:
    pipeline_type = profile.get("pipeline", "standard")
    opts = profile.get("options", {})

    if pipeline_type == "vlm":
        return _build_vlm_options(opts)
    return _build_standard_options(opts)


def _build_standard_options(opts: dict) -> PdfPipelineOptions:
    pipeline_opts = PdfPipelineOptions()
    pipeline_opts.do_ocr = opts.get("do_ocr", True)
    pipeline_opts.do_table_structure = opts.get("do_table_structure", True)

    if pipeline_opts.do_table_structure:
        pipeline_opts.table_structure_options = TableStructureOptions(
            do_cell_matching=opts.get("do_cell_matching", True),
        )

    ocr_engine = opts.get("ocr_engine", "easyocr")
    if ocr_engine != "easyocr":
        _apply_ocr_engine(pipeline_opts, ocr_engine)

    ocr_lang = opts.get("ocr_lang")
    if ocr_lang and hasattr(pipeline_opts.ocr_options, "lang"):
        pipeline_opts.ocr_options.lang = ocr_lang

    accelerator = opts.get("accelerator")
    if accelerator:
        from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
        pipeline_opts.accelerator_options = AcceleratorOptions(
            num_threads=accelerator.get("num_threads", 4),
            device=AcceleratorDevice(accelerator.get("device", "auto")),
        )

    return pipeline_opts


def _apply_ocr_engine(pipeline_opts: PdfPipelineOptions, engine: str) -> None:
    if engine == "tesseract":
        from docling.datamodel.pipeline_options import TesseractOcrOptions
        pipeline_opts.ocr_options = TesseractOcrOptions()
    elif engine == "ocrmac":
        from docling.datamodel.pipeline_options import OcrMacOptions
        pipeline_opts.ocr_options = OcrMacOptions()
    elif engine == "rapidocr":
        from docling.datamodel.pipeline_options import RapidOcrOptions
        pipeline_opts.ocr_options = RapidOcrOptions()
    elif engine == "tesseract_cli":
        from docling.datamodel.pipeline_options import TesseractCliOcrOptions
        pipeline_opts.ocr_options = TesseractCliOcrOptions()
    else:
        msg = f"Unknown OCR engine: {engine}"
        raise ValueError(msg)


def _build_vlm_options(opts: dict) -> VlmPipelineOptions:
    from docling.datamodel import vlm_model_specs
    from docling.pipeline.vlm_pipeline import VlmPipeline

    vlm_model = opts.get("vlm_model", "granite_docling")
    model_map = {
        "granite_docling": vlm_model_specs.GRANITEDOCLING_TRANSFORMERS,
        "smoldocling": vlm_model_specs.SMOLDOCLING_TRANSFORMERS,
        "granite_docling_vllm": vlm_model_specs.GRANITEDOCLING_VLLM,
    }

    vlm_spec = model_map.get(vlm_model)

    if vlm_model == "remote":
        from docling.datamodel.pipeline_options_vlm_model import ApiVlmOptions, ResponseFormat
        vlm_spec = ApiVlmOptions(
            url=opts["remote_url"],
            params=dict(
                model=opts.get("remote_model", "ibm-granite/granite-docling-258M"),
                max_tokens=opts.get("remote_max_tokens", 4096),
            ),
            response_format=ResponseFormat.DOCTAGS,
            timeout=opts.get("remote_timeout", 120),
        )
    elif vlm_model == "granite_docling_mlx":
        vlm_spec = vlm_model_specs.GRANITEDOCLING_MLX

    pipeline_options = VlmPipelineOptions(
        vlm_options=vlm_spec,
        generate_page_images=opts.get("generate_page_images", True),
        enable_remote_services=vlm_model == "remote",
    )

    pipeline_options.force_backend_text = opts.get("force_backend_text", False)

    return pipeline_options


def create_converter(
    profile_name: str,
    profiles: dict[str, dict] | None = None,
    profiles_path: str | Path = "profiles.yaml",
) -> DocumentConverter:
    if profiles is None:
        profiles = load_profiles(profiles_path)

    if profile_name not in profiles:
        available = ", ".join(profiles)
        msg = f"Unknown profile '{profile_name}'. Available: {available}"
        raise ValueError(msg)

    profile = profiles[profile_name]
    pipeline_options = _build_pipeline_options(profile)
    pipeline_type = profile.get("pipeline", "standard")

    if pipeline_type == "vlm":
        from docling.pipeline.vlm_pipeline import VlmPipeline
        fmt_opts: dict = {
            InputFormat.PDF: PdfFormatOption(
                pipeline_cls=VlmPipeline,
                pipeline_options=pipeline_options,
            ),
        }
    else:
        fmt_opts: dict = {
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options,
            ),
        }

    return DocumentConverter(format_options=fmt_opts)
