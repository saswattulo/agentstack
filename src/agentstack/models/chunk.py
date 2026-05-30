from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from agentstack.models.base import Base, TimestampMixin, UUIDPKMixin


class ChunkMetadata(Base, UUIDPKMixin, TimestampMixin):
    """Mirror of chunks indexed in Qdrant for joins, audit, and admin queries.

    The full text + vector live in Qdrant; this table stores the relational
    metadata so we can ask 'which chunks belong to which document' without
    paging Qdrant.
    """

    __tablename__ = "chunk_metadata"

    document_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    collection_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("collections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    qdrant_point_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content_preview: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extra: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
