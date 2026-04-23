from ..extensions import db
from ..time_utils import now_cordoba_naive


class PdfCache(db.Model):
    __tablename__ = "pdf_cache"

    id = db.Column(db.Integer, primary_key=True)
    lpg_document_id = db.Column(
        db.Integer,
        db.ForeignKey("lpg_document.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    pdf_base64 = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=now_cordoba_naive)

    document = db.relationship(
        "LpgDocument", backref=db.backref("pdf_cache", uselist=False)
    )
