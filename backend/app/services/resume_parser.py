"""
Resume Parser Service
- Extracts text from PDF and DOCX files
- Uses spaCy NER for personal info
- Uses FlashText against skills_database.json for skill extraction
- Returns structured JSON
"""
import os
import json
import re
from typing import Dict, Any, List

# PDF parsing
try:
    import PyPDF2
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

# DOCX parsing
try:
    from docx import Document as DocxDocument
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

# NLP
try:
    import spacy
    _nlp = spacy.load("en_core_web_sm")
    HAS_SPACY = True
except Exception:
    _nlp = None
    HAS_SPACY = False

# FlashText
try:
    from flashtext import KeywordProcessor
    HAS_FLASH = True
except ImportError:
    HAS_FLASH = False


class ResumeParser:
    def __init__(self, skills_db_path: str = None):
        self.nlp = _nlp
        self.keyword_processor = KeywordProcessor(case_sensitive=False) if HAS_FLASH else None

        # Load skills database
        self._skills: List[str] = []
        self._load_skills(skills_db_path)

    # --------------------------------------------------------
    # Skills loading
    # --------------------------------------------------------

    def _load_skills(self, path: str = None):
        if not path or not os.path.exists(path):
            # Try default location
            here = os.path.dirname(os.path.abspath(__file__))
            path = os.path.join(here, '..', '..', '..', 'data', 'skills_database.json')
            path = os.path.normpath(path)

        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                for category_skills in data.values():
                    self._skills.extend(category_skills)
            elif isinstance(data, list):
                self._skills = data
        else:
            # Fallback minimal list
            self._skills = [
                'Python', 'JavaScript', 'Java', 'C++', 'C#', 'TypeScript', 'Go', 'Rust',
                'React', 'Vue', 'Angular', 'Node.js', 'Flask', 'FastAPI', 'Django',
                'SQL', 'PostgreSQL', 'MySQL', 'MongoDB', 'Redis', 'SQLite',
                'Docker', 'Kubernetes', 'AWS', 'GCP', 'Azure', 'Terraform', 'CI/CD',
                'Machine Learning', 'Deep Learning', 'NLP', 'PyTorch', 'TensorFlow',
                'scikit-learn', 'Pandas', 'NumPy', 'Matplotlib', 'Tableau',
                'Git', 'GitHub', 'Linux', 'Bash', 'REST API', 'GraphQL',
                'Agile', 'Scrum', 'Jira', 'Communication', 'Leadership',
            ]

        if self.keyword_processor:
            for skill in self._skills:
                self.keyword_processor.add_keyword(skill)

    # --------------------------------------------------------
    # Text extraction
    # --------------------------------------------------------

    def extract_text_from_pdf(self, file_path: str) -> str:
        if not HAS_PYPDF:
            return ""
        text_parts = []
        try:
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text_parts.append(page.extract_text() or '')
        except Exception as e:
            print(f"[ResumeParser] PDF error: {e}")
        return '\n'.join(text_parts)

    def extract_text_from_docx(self, file_path: str) -> str:
        if not HAS_DOCX:
            return ""
        try:
            doc = DocxDocument(file_path)
            return '\n'.join(p.text for p in doc.paragraphs)
        except Exception as e:
            print(f"[ResumeParser] DOCX error: {e}")
            return ""

    def extract_text(self, file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.pdf':
            return self.extract_text_from_pdf(file_path)
        elif ext in ('.doc', '.docx'):
            return self.extract_text_from_docx(file_path)
        elif ext == '.txt':
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        return ""

    # --------------------------------------------------------
    # Skill extraction
    # --------------------------------------------------------

    def extract_skills(self, text: str) -> List[str]:
        if self.keyword_processor:
            found = self.keyword_processor.extract_keywords(text)
            # Deduplicate preserving original casing from skills list
            seen = set()
            result = []
            for s in found:
                ls = s.lower()
                if ls not in seen:
                    seen.add(ls)
                    result.append(s)
            return result
        # Fallback: simple substring match
        text_lower = text.lower()
        return [s for s in self._skills if s.lower() in text_lower]

    # --------------------------------------------------------
    # Personal info extraction (regex + spaCy)
    # --------------------------------------------------------

    def extract_personal_info(self, text: str) -> Dict[str, str]:
        info: Dict[str, str] = {}

        # Email
        emails = re.findall(r'[\w.\-+]+@[\w.\-]+\.\w{2,}', text)
        if emails:
            info['email'] = emails[0]

        # Phone
        phones = re.findall(
            r'(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)?\d{3}[\s.-]?\d{4}', text)
        if phones:
            info['phone'] = phones[0].strip()

        # LinkedIn
        linkedin = re.findall(r'linkedin\.com/in/[\w\-]+', text, re.IGNORECASE)
        if linkedin:
            info['linkedin'] = 'https://' + linkedin[0]

        # GitHub
        github = re.findall(r'github\.com/[\w\-]+', text, re.IGNORECASE)
        if github:
            info['github'] = 'https://' + github[0]

        # Try spaCy for name / location
        if self.nlp and HAS_SPACY:
            doc = self.nlp(text[:2000])  # Only first 2k chars for speed
            persons  = [e.text for e in doc.ents if e.label_ == 'PERSON']
            gpes     = [e.text for e in doc.ents if e.label_ == 'GPE']
            if persons:
                info['name'] = persons[0]
            if gpes:
                info['location'] = gpes[0]

        return info

    # --------------------------------------------------------
    # Section extraction (heuristic)
    # --------------------------------------------------------

    _SECTION_PATTERNS = {
        'experience': re.compile(
            r'(?:work\s+)?experience|employment\s+history|professional\s+background',
            re.IGNORECASE),
        'education': re.compile(
            r'education(?:al)?\s*(?:background|history)?|academic\s+(?:background|history)',
            re.IGNORECASE),
        'skills': re.compile(
            r'(?:technical\s+)?skills|competencies|technologies|tools',
            re.IGNORECASE),
        'certifications': re.compile(
            r'certifications?|certificates?|credentials?|licen[cs]e',
            re.IGNORECASE),
    }

    def _split_sections(self, text: str) -> Dict[str, str]:
        lines = text.split('\n')
        sections: Dict[str, List[str]] = {'header': [], 'experience': [],
                                           'education': [], 'skills': [],
                                           'certifications': [], 'other': []}
        current = 'header'
        header_done = False

        for line in lines:
            stripped = line.strip()
            if not stripped:
                sections[current].append('')
                continue

            matched = False
            for sec, pat in self._SECTION_PATTERNS.items():
                if pat.match(stripped) and len(stripped) < 60:
                    current = sec
                    header_done = True
                    matched = True
                    break

            if not matched:
                if not header_done and len(sections['header']) < 8:
                    sections['header'].append(stripped)
                else:
                    sections[current].append(stripped)

        return {k: '\n'.join(v) for k, v in sections.items()}

    # --------------------------------------------------------
    # Main parse function
    # --------------------------------------------------------

    def parse(self, file_path: str) -> Dict[str, Any]:
        text = self.extract_text(file_path)
        if not text.strip():
            return {'error': 'Could not extract text from file', 'raw_text': ''}

        personal   = self.extract_personal_info(text)
        skills     = self.extract_skills(text)
        sections   = self._split_sections(text)

        return {
            'raw_text': text,
            'personal': personal,
            'skills':   skills,
            'sections': sections,
            'skill_count': len(skills),
        }

    def parse_from_text(self, text: str) -> Dict[str, Any]:
        """Parse when raw text is already available (no file)."""
        personal   = self.extract_personal_info(text)
        skills     = self.extract_skills(text)
        sections   = self._split_sections(text)

        return {
            'raw_text': text,
            'personal': personal,
            'skills':   skills,
            'sections': sections,
            'skill_count': len(skills),
        }
