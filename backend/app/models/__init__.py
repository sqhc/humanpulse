"""模型登记：导入后 Base.metadata 才包含全部表（Alembic 依赖它）。"""

from app.models.analysis import Analysis, Cluster, ClusterMember, Embedding
from app.models.base import Base, TimestampMixin
from app.models.document import Document, FetchRun
from app.models.ops import LlmUsageDay, ManualUpload, TakedownRequest
from app.models.source import Source, SourceCursor
from app.models.summary import Brief, BriefItem

__all__ = [
    "Analysis",
    "Base",
    "Brief",
    "BriefItem",
    "Cluster",
    "ClusterMember",
    "Document",
    "Embedding",
    "FetchRun",
    "LlmUsageDay",
    "ManualUpload",
    "Source",
    "SourceCursor",
    "TakedownRequest",
    "TimestampMixin",
]
