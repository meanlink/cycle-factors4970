from sqlalchemy import String, Double, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base
class Report(Base):
    __tablename__ = 'reports'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    job_id: Mapped[int] = mapped_column(ForeignKey('jobs.id'))
    job_name: Mapped[str] = mapped_column(String(160), default='')
    combination_id: Mapped[int | None] = mapped_column(ForeignKey('combinations.id'), nullable=True)
    combination_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    combination_version_no: Mapped[int | None] = mapped_column(nullable=True)
    sample_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    destination: Mapped[str] = mapped_column(String(120))
    interval_seconds: Mapped[int]
    next_run: Mapped[float] = mapped_column(Double)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
class Delivery(Base):
    __tablename__ = 'deliveries'
    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey('reports.id'))
    job_id: Mapped[int | None] = mapped_column(ForeignKey('jobs.id'), nullable=True)
    job_name: Mapped[str] = mapped_column(String(160), default='')
    combination_id: Mapped[int | None] = mapped_column(ForeignKey('combinations.id'), nullable=True)
    combination_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    combination_version_no: Mapped[int | None] = mapped_column(nullable=True)
    sample_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[float] = mapped_column(Double)
    checksum: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(160))
    destination: Mapped[str] = mapped_column(String(120))
