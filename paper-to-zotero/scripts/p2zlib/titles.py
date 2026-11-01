"""Attachment titles: the grammar paper-fetch writes a file's label in and paper-to-zotero reads it back by.

<Version>-<Source>-<detail>..., such as Preprint-arXiv-v7, Accepted-CVF, Published-Elsevier-in_press, Snapshot-IEEE,
Unknown. Fields are separated by "-"; inside a field, spaces and hyphens become "_" (Europe_PMC,
ICLR_2027_submission). The version word is one of VERSIONS, capitalized; the source is a short brand name in its own
spelling; detail fields come only after a source, so without one the title is the version word alone. A version
the agent could not settle is Unknown: the file is attached all the same. SOURCES and the detail words (vN,
in_press, ICLR_2023, ICLR_2027_submission, source_data, abstract_booklet_p66) are a starting set the agent extends
on the same pattern. A title outside this scheme (Zotero's "Full Text PDF", an older run's "Preprint (arXiv)") says
nothing about the version.

paper-fetch owns this file; paper-to-zotero carries a byte-for-byte copy (p2zlib/titles.py), and a test there fails
when the two differ.
"""
import re

VERSIONS = ("Published", "Accepted", "Preprint", "Unknown", "Supplement", "Snapshot")
TITLE_RE = re.compile(r"^(" + "|".join(VERSIONS) + r")((?:-[\w.]+)*)$")
# Where a file came from, by host (a parent domain covers its subdomains) -> its source in the title. A starting
# table: a site not here gets its name from the agent, on the same pattern.
SOURCES = {
    "arxiv.org": "arXiv", "biorxiv.org": "bioRxiv", "medrxiv.org": "medRxiv", "ssrn.com": "SSRN",
    "researchsquare.com": "Research_Square", "openreview.net": "OpenReview", "thecvf.com": "CVF", "ecva.net": "ECVA",
    "papers.miccai.org": "MICCAI", "neurips.cc": "NeurIPS", "nips.cc": "NeurIPS", "mlr.press": "PMLR",
    "iclr.cc": "ICLR", "aclanthology.org": "ACL", "aaai.org": "AAAI", "jmlr.org": "JMLR", "ieee.org": "IEEE",
    "sciencedirect.com": "Elsevier", "sciencedirectassets.com": "Elsevier", "elsevier.com": "Elsevier",
    "springer.com": "Springer", "nature.com": "Nature", "acm.org": "ACM", "wiley.com": "Wiley", "rsna.org": "RSNA",
    "bmj.com": "BMJ", "nejm.org": "NEJM", "science.org": "Science", "mdpi.com": "MDPI", "jmir.org": "JMIR",
    "academic.oup.com": "OUP", "pmc.ncbi.nlm.nih.gov": "PMC", "ncbi.nlm.nih.gov": "PMC", "europepmc.org": "Europe_PMC",
    "hal.science": "HAL", "archives-ouvertes.fr": "HAL", "escholarship.org": "eScholarship",
    "researchgate.net": "ResearchGate", "easychair.org": "EasyChair", "cell.com": "Elsevier", "thelancet.com": "Elsevier",
    "pnas.org": "PNAS", "plos.org": "PLOS", "iop.org": "IOP", "spiedigitallibrary.org": "SPIE", "thieme-connect.com": "Thieme",
    "thieme-connect.de": "Thieme", "biomedcentral.com": "BMC", "frontiersin.org": "Frontiers", "lirias.kuleuven.be": "Lirias",
    "proquest.com": "ProQuest", "ebscohost.com": "EBSCO", "ovid.com": "Ovid",
}


def title_field(text):
    """One field of an attachment title: spaces and hyphens become "_", characters other than letters, digits, "_"
    and "." are dropped ("Europe PMC" -> "Europe_PMC", "T-CAIREM" -> "T_CAIREM")."""
    s = re.sub(r"[^\w.]", "", re.sub(r"[\s\-]+", "_", str(text or "").strip()))
    return re.sub(r"_+", "_", s).strip("_.")


def label_title(version, source=None, detail=()):
    """The title of a file of this version (a word of VERSIONS, any case) from this source with this detail:
    "Preprint-arXiv-v7"; without a source, the version word alone."""
    word = next((v for v in VERSIONS if v.lower() == str(version).lower()), None)
    if word is None:
        raise ValueError(f"not a version: {version!r}; one of {', '.join(VERSIONS)}")
    source = title_field(source)
    return "-".join([word, source, *filter(None, map(title_field, detail))]) if source else word


def parse_title(title):
    """A title in the scheme -> {version (lowercase), source, detail: [fields]}; None for any other title."""
    m = TITLE_RE.match((title or "").strip())
    if not m:
        return None
    fields = m.group(2).split("-")[1:]
    return {"version": m.group(1).lower(), "source": fields[0] if fields else None, "detail": fields[1:]}
