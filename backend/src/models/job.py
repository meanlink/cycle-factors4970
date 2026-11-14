from sqlalchemy import String, JSON, Double, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base
class Job(Base):
    __tablename__ = 'jobs'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    dataset_id: Mapped[int | None] = mapped_column(ForeignKey('datasets.id'), nullable=True)
    combination_id: Mapped[int | None] = mapped_column(ForeignKey('combinations.id'), nullable=True)
    combination_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    combination_version_id: Mapped[int | None] = mapped_column(ForeignKey('combination_versions.id'), nullable=True)
    combination_version_no: Mapped[int | None] = mapped_column(nullable=True)
    sample_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Copied from the combination version when the job is created; later
    # combination edits never touch queued or running jobs.
    samples: Mapped[list | None] = mapped_column(JSON, nullable=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default='queued')
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(String(1000), default='')
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[float] = mapped_column(Double)
    finished_at: Mapped[float | None] = mapped_column(Double, nullable=True)
