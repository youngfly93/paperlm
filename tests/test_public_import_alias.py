from paperlm.engines.ocr_adapter import OCRAdapter
from paperlm.workers import DoclingWorkerPool

import markitdown_paperlm
import paperlm
from markitdown_paperlm.engines.ocr_adapter import OCRAdapter as InternalOCRAdapter
from markitdown_paperlm.workers import DoclingWorkerPool as InternalDoclingWorkerPool


def test_public_paperlm_import_alias() -> None:
    assert paperlm.__version__ == markitdown_paperlm.__version__
    assert paperlm.register_converters is markitdown_paperlm.register_converters
    assert OCRAdapter is InternalOCRAdapter
    assert DoclingWorkerPool is InternalDoclingWorkerPool
