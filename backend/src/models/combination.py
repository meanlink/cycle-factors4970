from sqlalchemy import String, JSON, Double, ForeignKey, Integer, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base


class Combination(Base):
    """A named, versioned combination of immutable observation batches.

    ``current_version_id`` intentionally has no database foreign key: the
    version row also points back at the combination, and keeping the pointer as
    a plain integer avoids a circular FK while still letting us lock the
    combination row during concurrent edits.
    """
    __tablename__ = 'combinations'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[float] = mapped_column(Double)
    current_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class CombinationVersion(Base):
    """Immutable resolved snapshot of one combination revision.

    Samples are materialised at version creation time. Jobs copy this list so
    a queued analysis never observes a later combination edit.
    """
    __tablename__ = 'combination_versions'
    __table_args__ = (UniqueConstraint('combination_id', 'version_no', name='uq_combination_version'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    combination_id: Mapped[int] = mapped_column(ForeignKey('combinations.id'))
    version_no: Mapped[int] = mapped_column(Integer)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[float] = mapped_column(Double)
    dataset_ids: Mapped[list] = mapped_column(JSON, default=list)
    dataset_meta: Mapped[list] = mapped_column(JSON, default=list)
    resolutions: Mapped[dict] = mapped_column(JSON, default=dict)
    conflicts: Mapped[list] = mapped_column(JSON, default=list)
    samples: Mapped[list] = mapped_column(JSON, default=list)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    ready: Mapped[bool] = mapped_column(Boolean, default=False)
    sample_checksum: Mapped[str] = mapped_column(String(64), default='')
    checksum: Mapped[str] = mapped_column(String(64), default='')
