#!/usr/bin/env python3
"""
PDFs-AI-Rename - Enhanced AI-powered document renamer
Supports PDF, EPUB, DOCX with comprehensive filename cleaning and normalization.
"""

import os
import sys
import zipfile
import xml.etree.ElementTree as ET
import re
import time
from pathlib import Path
from typing import Optional, Dict, List, Set

try:
    import tiktoken
except ImportError:
    print("📦 Installing tiktoken...")
    os.system("pip3 install --user -q tiktoken")
    import tiktoken

try:
    from PyPDF2 import PdfReader
except ImportError:
    print("📦 Installing PyPDF2...")
    os.system("pip3 install --user -q PyPDF2")
    from PyPDF2 import PdfReader

try:
    from openai import OpenAI
except ImportError:
    print("📦 Installing openai...")
    os.system("pip3 install --user -q openai")
    from openai import OpenAI

try:
    from docx import Document
except ImportError:
    print("📦 Installing python-docx...")
    os.system("pip3 install --user -q python-docx")
    from docx import Document

client = OpenAI()
max_length = 15000

# =============================================================================
# COMPREHENSIVE ACRONYM LIST
# =============================================================================
ACRONYMS = {
    # Therapeutic Modalities
    'DBT', 'CBT', 'ACT', 'RFT', 'FAP', 'EMDR', 'IFS', 'EFT', 'AEDP', 'ISTDP', 'IPT',
    'REBT', 'CFT', 'PCT', 'SFT', 'CPT', 'PE', 'MBCT', 'MBSR', 'MI', 'MET',
    'SFBT', 'BT', 'RT', 'GT', 'AT', 'PT', 'CT', 'ST', 'NT', 'SE', 'TF',
    'CBASP', 'BATD', 'BA', 'ABBT', 'IBCT', 'TBCT', 'ERP', 'EXRP', 'NLP', 'RO', 'RODBT',
    'PRT', 'FFT',
    # Disorders & Diagnoses  
    'PTSD', 'CPTSD', 'OCD', 'ADHD', 'ADD', 'BPD', 'NPD', 'APD', 'ASPD', 'HPD', 'OCPD',
    'MDD', 'GAD', 'SAD', 'PMDD', 'PDD', 'ASD', 'SUD', 'AUD', 'DID', 'DPDR',
    'AN', 'BN', 'BED', 'ARFID', 'ED', 'SIB', 'NSSI', 'TBI', 'CTE', 'DUI',
    # Diagnostic Manuals & Standards
    'DSM', 'DSM5', 'DSMV', 'DSMIV', 'TR', 'ICD', 'ICD10', 'ICD11', 'PDM',
    # Professional/Credentials
    'APA', 'ACA', 'NASW', 'NBCC', 'NCC', 'ACS', 'CRC', 'LMHC', 'LCSW', 'LPC', 'LMFT',
    'LCPC', 'LPCC', 'PCC', 'MCC', 'ACC', 'PHD', 'PSYD', 'EDD', 'MD', 'DO', 'RN', 'NP',
    'MBA', 'CEO', 'CFO', 'CTO', 'EAP',
    # Research & Assessment
    'RCT', 'ABA', 'FBA', 'BIP', 'IEP', 'WAIS', 'WISC', 'MMPI', 'MCMI', 'BDI', 'BAI',
    'PHQ', 'GAD7', 'PCL', 'ACE', 'ACES', 'AUDIT', 'DAST', 'CAGE', 'DASS',
    'KABC', 'SDS', 'MBTI', 'CPCE', 'NCE', 'CACREP',
    # Organizations
    'WHO', 'HBR', 'NIH', 'CDC', 'NIMH', 'SAMHSA', 'FDA', 'NATO', 'NASA', 'UN', 'EU',
    # Clinical/Medical
    'SOAP', 'HIPAA', 'FERPA', 'PHI', 'EHR', 'EMR', 'ROI', 'TIC', 'DEI',
    'LGBTQ', 'LGBTQIA', 'LGBT', 'HIV', 'AIDS', 'STI', 'STD',
    'DNA', 'RNA', 'MRI', 'CT', 'EEG', 'ECG', 'ICU', 'ER',
    # Tech/General
    'AI', 'ML', 'GPT', 'API', 'SQL', 'HTML', 'CSS', 'IPA', 'OK',
    'PDF', 'EPUB', 'ISBN', 'USA', 'UK', 'US', 'FBI', 'CIA',
    'NBA', 'NFL', 'MLB', 'NHL',
    'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII'
}

# =============================================================================
# FILENAME CLEANER CLASS
# =============================================================================
class FilenameCleaner:
    """Professional-grade filename cleaning with pattern detection."""
    
    # Pattern definitions for cleaning
    PATTERNS = {
        'uuid_suffix': (re.compile(r'[_\-\s]?[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', re.IGNORECASE), ''),
        'year_prefix': (re.compile(r'^[\(\[]?(19|20)\d{2}[\)\]]?\s*[-–—]?\s*'), ''),
        'doc_id_prefix': (re.compile(r'^(DOC|ID|FILE|SCAN)?[_\-]?\d{5,}[_\-\s]+', re.IGNORECASE), ''),
        'platform_markers': (re.compile(r'\b(Blinkist|TeAM\s*YYePG|z-lib|libgen|b-ok|bookzz|sci-hub|mobilism|epubdump)\b', re.IGNORECASE), ''),
        'placeholder_authors': (re.compile(r'\s*[-–—]\s*(Many|Unknown|Various|Anonymous|Multiple\s*Authors?|N/?A|None|TBD|Author)\s*$', re.IGNORECASE), ''),
        'hash_suffix': (re.compile(r'[_\-\s]?[\[\(][a-f0-9]{6,}[\]\)]', re.IGNORECASE), ''),
        'numeric_prefix': (re.compile(r'^\d{1,4}[_\-\.\s]+(?=[A-Za-z])'), ''),
        'url_remnants': (re.compile(r'(?:https?://|www\.)[^\s_]+[_\s]*', re.IGNORECASE), ''),
        'bracketed_junk': (re.compile(r'\s*[\[\(](PDF|EPUB|MOBI|AZW3?|Kindle|Ebook|eBook|Digital|Scan|OCR|Retail|True\s*PDF)[\]\)]', re.IGNORECASE), ''),
        'release_tags': (re.compile(r'[_\-]\s*[A-Z]{2,10}$'), ''),
        'duplicate_suffix': (re.compile(r'[_\-\s]?\(?\d{1,2}\)?$'), ''),
        'ellipsis': (re.compile(r'\.{2,}$|…$'), ''),
        'underscores': (re.compile(r'_+'), ' '),
        'double_spaces': (re.compile(r'\s{2,}'), ' '),
    }
    
    # HTML entity mapping
    HTML_ENTITIES = {
        '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"',
        '&apos;': "'", '&nbsp;': ' ', '&#39;': "'", '&#34;': '"'
    }
    
    # Contractions
    CONTRACTIONS = {
        'Dont': "Don't", 'Doesnt': "Doesn't", 'Cant': "Can't", 'Wont': "Won't",
        'Wouldnt': "Wouldn't", 'Couldnt': "Couldn't", 'Shouldnt': "Shouldn't",
        'Didnt': "Didn't", 'Wasnt': "Wasn't", 'Werent': "Weren't",
        'Isnt': "Isn't", 'Arent': "Aren't", 'Hasnt': "Hasn't",
        'Havent': "Haven't", 'Hadnt': "Hadn't",
        'Youre': "You're", 'Youve': "You've", 'Youll': "You'll",
        'Theyre': "They're", 'Theyve': "They've", 'Theyll': "They'll",
        'Weve': "We've", 'Ive': "I've", 'Im': "I'm",
        'Hes': "He's", 'Shes': "She's",
        'Thats': "That's", 'Whats': "What's", 'Whos': "Who's",
        'Wheres': "Where's", 'Heres': "Here's", 'Theres': "There's",
        'Lets': "Let's",
    }
    
    # Possessive suffixes
    POSSESSIVE_SUFFIXES = ['Guide', 'Notebook', 'Manual', 'Handbook', 'Thesaurus', 
                          'Workbook', 'Companion', 'Primer', 'Desk Reference']
    
    # Named possessives
    NAMED_POSSESSIVES = {
        'Aspergers': "Asperger's", 'Alzheimers': "Alzheimer's", 'Parkinsons': "Parkinson's",
        'Becks': "Beck's", 'Garfields': "Garfield's", 'Sadocks': "Sadock's",
        'Kaplans': "Kaplan's", 'Freuds': "Freud's", 'Jungs': "Jung's",
        'Ericksons': "Erickson's", 'Bowlbys': "Bowlby's", 'Piagets': "Piaget's",
        'Maslows': "Maslow's", 'Skinners': "Skinner's", 'Banduras': "Bandura's",
        'Yaloms': "Yalom's", 'Gottmans': "Gottman's", 'Seligmans': "Seligman's",
        'Linehans': "Linehan's", 'Rogers': "Rogers'",
    }
    
    def clean(self, text: str) -> str:
        """Apply all cleaning rules to text."""
        if not text:
            return text
        
        original = text
        
        # HTML entities
        for entity, replacement in self.HTML_ENTITIES.items():
            text = text.replace(entity, replacement)
        
        # Apply pattern-based cleaning
        for name, (pattern, replacement) in self.PATTERNS.items():
            text = pattern.sub(replacement, text)
        
        # Fix contractions
        text = self._fix_contractions(text)
        
        # Fix possessives
        text = self._fix_possessives(text)
        
        # Fix named possessives
        text = self._fix_named_possessives(text)
        
        # Remove incorrect apostrophes from plurals
        text = self._fix_incorrect_apostrophes(text)
        
        # Convert title-subtitle separators to em dash
        text = re.sub(r'\s+[-–]\s+', ' — ', text)
        text = re.sub(r':\s+', ' — ', text)
        
        # Capitalize first word after em dash
        text = re.sub(r'(— )(\w)', lambda m: m.group(1) + m.group(2).upper(), text)
        
        # Final cleanup
        text = re.sub(r'\s+', ' ', text).strip()
        text = re.sub(r'^[\s\-_.,;:]+|[\s\-_.,;:]+$', '', text)
        
        return text
    
    def _fix_contractions(self, text: str) -> str:
        words = text.split()
        result = []
        for word in words:
            clean_word = re.sub(r'[^\w]$', '', word)
            trailing = word[len(clean_word):] if len(word) > len(clean_word) else ''
            if clean_word in self.CONTRACTIONS:
                result.append(self.CONTRACTIONS[clean_word] + trailing)
            else:
                result.append(word)
        return ' '.join(result)
    
    def _fix_possessives(self, text: str) -> str:
        for suffix in self.POSSESSIVE_SUFFIXES:
            pattern = re.compile(rf'\b(\w+?)s\s+({suffix})\b', re.IGNORECASE)
            def replace_possessive(match):
                word = match.group(1)
                suf = match.group(2)
                if len(word) >= 3:
                    return f"{word}'s {suf}"
                return match.group(0)
            text = pattern.sub(replace_possessive, text)
        return text
    
    def _fix_named_possessives(self, text: str) -> str:
        for wrong, correct in self.NAMED_POSSESSIVES.items():
            pattern = re.compile(rf'\b{wrong}\b', re.IGNORECASE)
            text = pattern.sub(correct, text)
        return text
    
    def _fix_incorrect_apostrophes(self, text: str) -> str:
        plural_words = [
            'Teens', 'Skills', 'Parents', 'Therapists', 'Clients', 'Patients',
            'Children', 'Adults', 'Couples', 'Families', 'Groups', 'Sessions',
            'Boundaries', 'Activities', 'Exercises', 'Techniques', 'Strategies',
            'Tools', 'Methods', 'Approaches', 'Interventions', 'Treatments',
        ]
        for word in plural_words:
            singular = word.rstrip('s')
            possessive_indicators = '|'.join(self.POSSESSIVE_SUFFIXES)
            pattern = re.compile(rf"\b{singular}'s\b(?!\s+({possessive_indicators}))", re.IGNORECASE)
            text = pattern.sub(word, text)
        
        # Fix misspellings
        incorrect_patterns = [
            (r"\bBoundarie's\b", "Boundaries"),
            (r"\bActivitie's\b", "Activities"),
        ]
        for pattern, replacement in incorrect_patterns:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
        return text


# Initialize cleaner
cleaner = FilenameCleaner()

# =============================================================================
# APPOINTMENT/CLINICAL DOCUMENT DETECTION
# =============================================================================
APPOINTMENT_KEYWORDS = [
    'appointment', 'session', 'intake', 'progress note', 'clinical note',
    'therapy', 'counseling', 'treatment', 'assessment', 'evaluation',
    'consultation', 'telehealth', 'superbill', 'invoice', 'receipt',
    'statement', 'claim', 'insurance', 'copay', 'diagnosis',
]

def is_appointment_document(content, filename=""):
    """Detect if a document is an appointment/clinical/billing document."""
    combined = (content + " " + filename).lower()
    return any(kw in combined for kw in APPOINTMENT_KEYWORDS)

# =============================================================================
# TITLE CASE WITH ACRONYMS
# =============================================================================
def apply_title_case(text: str) -> str:
    """Apply title case while preserving acronyms and handling hyphens."""
    if not text:
        return text
    
    small_words = {'a', 'an', 'the', 'and', 'but', 'or', 'for', 'nor', 
                   'on', 'at', 'to', 'from', 'by', 'in', 'of', 'with'}
    
    words = text.split()
    result = []
    
    for i, word in enumerate(words):
        # Handle hyphenated words
        if '-' in word:
            parts = word.split('-')
            hyphenated_result = []
            for p in parts:
                if p.upper() in ACRONYMS:
                    hyphenated_result.append(p.upper())
                elif p.isdigit():
                    hyphenated_result.append(p)
                else:
                    hyphenated_result.append(p.capitalize())
            result.append('-'.join(hyphenated_result))
        elif word.upper() in ACRONYMS:
            result.append(word.upper())
        elif i == 0 or i == len(words) - 1 or word.lower() not in small_words:
            result.append(word.capitalize())
        else:
            result.append(word.lower())
    
    return ' '.join(result)

# =============================================================================
# OPENAI TITLE GENERATION
# =============================================================================
def get_new_filename_from_openai(content, is_filename_only=False, original_filename=""):
    acronym_rule = ("Keep standard acronyms in ALL CAPS, such as: "
        "CBT, DBT, ACT, MI, PTSD, EMDR, OCD, ADHD, ASD, BPD, GAD, MDD, "
        "LGBTQ, SOAP, DSM, DSM-5, DSM-5-TR, ICD, PHQ, BAI, BDI, PCL, ACE, HIPAA, "
        "ERP, CPT, PE, TF, SUD, IPT, EAP, APA, NIH, WHO, FDA, RFT, FAP, IFS, "
        "AI, API, PDF, MMPI, MCMI, WAIS, WISC, MBTI, MBSR, MBCT, NLP, CFT, EFT.")

    if is_appointment_document(content, original_filename):
        system_msg = (
            "You are a helpful assistant. Given a clinical or appointment-related document, "
            "extract the person's full name, the document type (e.g. Appointment, Intake, "
            "Progress Note, Superbill, Invoice, Statement, Assessment), and any date found. "
            "Output the filename in this exact format: 'Firstname Lastname DocumentType M-DD-YYYY'. "
            f"{acronym_rule} "
            "Use only English letters, numbers, spaces, and hyphens. Max 80 characters. "
            "Reply with just the filename, no extension, no explanation."
        )
    else:
        strip_rule = ("ONLY output the title of the work. Strip ALL author names, publisher names, "
            "edition info, series info, ISBNs, dates, and any other metadata. "
            "Use hyphens for hyphenated words like Self-Compassion or Evidence-Based. "
            "Use an em dash (—) between main title and subtitle.")
        if is_filename_only:
            system_msg = f"You are a helpful assistant. Given a filename, extract ONLY the title and output it in Title Case. {strip_rule} {acronym_rule} Use only English letters, numbers, spaces, and hyphens. Max 80 characters. Reply with just the title, no extension, no explanation."
        else:
            system_msg = f"You are a helpful assistant. Given document content, identify the title and output ONLY the title in Title Case. {strip_rule} {acronym_rule} Use only English letters, numbers, spaces, and hyphens. Max 80 characters. Reply with just the title, no extension, no explanation."

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": content[:4000]}  # Limit content size
        ],
        temperature=0.1,
        max_tokens=150
    )
    initial_filename = response.choices[0].message.content
    filename = validate_and_trim_filename(initial_filename)
    return filename

# =============================================================================
# FILENAME VALIDATION AND CLEANUP
# =============================================================================
def validate_and_trim_filename(initial_filename):
    if not initial_filename:
        timestamp = time.strftime('%Y%m%d%H%M%S', time.gmtime())
        return f'empty_file_{timestamp}'

    # Apply comprehensive cleaning
    cleaned = cleaner.clean(initial_filename)
    
    # Strip underscores, replace with spaces
    cleaned = cleaned.replace('_', ' ')
    
    # Remove anything that isn't a letter, number, space, hyphen, or em dash
    cleaned = re.sub(r'[^A-Za-z0-9 \-—\']', '', cleaned).strip()
    
    if not cleaned:
        timestamp = time.strftime('%Y%m%d%H%M%S', time.gmtime())
        return f'Unnamed {timestamp}'
    
    # Collapse multiple spaces
    cleaned = re.sub(r' +', ' ', cleaned)
    
    # Apply title case with acronym handling
    cleaned = apply_title_case(cleaned)
    
    return cleaned if len(cleaned) <= 100 else cleaned[:100].strip()

# =============================================================================
# UNHELPFUL NAME DETECTION
# =============================================================================
UNHELPFUL_NAMES = {
    'no title found', 'no title detected', 'no title', 'unknown', 'unnamed',
    'untitled', 'unavailable', 'missing', 'empty', 'blank',
    'unable to process', 'no content', 'not available', 'n a', 'na',
    'none', 'null', 'missing person', 'title not found',
}

UNHELPFUL_PHRASES = [
    'im sorry', "i'm sorry", 'i cannot', 'i need a', 'unable to',
    'please provide', 'cannot generate', 'no response', 'without any content',
]

def is_unhelpful_name(name):
    lower = name.lower().strip()
    for bad in UNHELPFUL_NAMES:
        if lower == bad or lower.startswith(bad):
            return True
    for phrase in UNHELPFUL_PHRASES:
        if phrase in lower:
            return True
    if len(lower) > 80:
        return True
    return False

# =============================================================================
# TEXT EXTRACTION
# =============================================================================
def pdf_to_text(filepath):
    with open(filepath, 'rb') as file:
        reader = PdfReader(file)
        content = ""
        for page in reader.pages[:5]:  # First 5 pages
            text = page.extract_text()
            if text and text.strip():
                content += text + "\n"
                if len(content) >= 500:
                    break
        if content.strip():
            encoding = tiktoken.get_encoding("cl100k_base")
            num_tokens = len(encoding.encode(content))
            if num_tokens > max_length:
                content = content_token_cut(content, num_tokens, max_length)
            return content
        meta = reader.metadata
        if meta:
            title = meta.get('/Title') or meta.get('Title')
            if title and title.strip():
                return f"METADATA_TITLE:{title.strip()}"
        return None

def epub_to_title(filepath):
    """Extract title from epub metadata via OPF file."""
    try:
        with zipfile.ZipFile(filepath) as z:
            for name in z.namelist():
                if name.endswith('.opf'):
                    with z.open(name) as f:
                        tree = ET.parse(f)
                        root = tree.getroot()
                        ns = {
                            'opf': 'http://www.idpf.org/2007/opf',
                            'dc': 'http://purl.org/dc/elements/1.1/',
                        }
                        title_el = root.find('.//dc:title', ns)
                        if title_el is not None and title_el.text and title_el.text.strip():
                            return title_el.text.strip()
    except Exception:
        pass
    return None

def docx_to_text(filepath):
    """Extract text from DOCX file."""
    try:
        doc = Document(filepath)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return '\n'.join(paragraphs[:50])  # First 50 paragraphs
    except Exception:
        return None

def content_token_cut(content, num_tokens, max_length):
    content_length = len(content)
    while num_tokens > max_length:
        ratio = num_tokens / max_length
        new_length = int(content_length * num_tokens * (90 / 100))
        content = content[:new_length]
        num_tokens = len(tiktoken.get_encoding("cl100k_base").encode(content))
    return content

# =============================================================================
# MAIN PROCESSING
# =============================================================================
def rename_files_in_directory(directory):
    files = [f for f in os.listdir(directory)
             if os.path.isfile(os.path.join(directory, f)) and not f.startswith("._")]
    files.sort(key=lambda x: os.path.getmtime(os.path.join(directory, x)), reverse=True)

    if not files:
        print("No files found in directory.")
        return

    # Pre-pass: strip trailing numerals like " 2", " 3", "_01" from previous runs
    for filename in files:
        name, ext = os.path.splitext(filename)
        stripped = re.sub(r'[_ ]\d{1,2}$', '', name).strip()
        if stripped != name:
            stripped_filename = stripped + ext
            if stripped_filename not in files and not os.path.exists(os.path.join(directory, stripped_filename)):
                old_path = os.path.join(directory, filename)
                new_path = os.path.join(directory, stripped_filename)
                try:
                    os.rename(old_path, new_path)
                    print(f"  🧹 Cleaned suffix: {filename} -> {stripped_filename}")
                except Exception:
                    pass

    # Refresh file list after cleanup
    files = [f for f in os.listdir(directory)
             if os.path.isfile(os.path.join(directory, f)) and not f.startswith("._")]
    files.sort(key=lambda x: os.path.getmtime(os.path.join(directory, x)), reverse=True)

    # Filter to supported extensions
    supported_extensions = {'.pdf', '.epub', '.docx'}
    files = [f for f in files if os.path.splitext(f)[1].lower() in supported_extensions]

    print(f"📚 Found {len(files)} files to process.")
    
    renamed_count = 0
    skipped_count = 0
    failed_count = 0
    
    for filename in files:
        filepath = os.path.join(directory, filename)
        name, ext = os.path.splitext(filename)
        ext_lower = ext.lower()

        print(f"\n📄 Processing: {filename}")

        # Clean _01, _02 etc. suffixes from name for AI input
        clean_name = re.sub(r'[_ ]\d{1,2}$', '', name).strip()
        
        # Apply pre-cleaning to filename
        clean_name = cleaner.clean(clean_name)

        # Extract content based on file type
        content = None
        is_filename_only = False

        if ext_lower == ".pdf":
            try:
                content = pdf_to_text(filepath)
                if content is not None and content.startswith("METADATA_TITLE:"):
                    meta_title = content.replace("METADATA_TITLE:", "")
                    print(f"  📖 Found metadata title: {meta_title}")
                    content = meta_title
                    is_filename_only = True
                elif content is None:
                    print(f"  ⚠️ PDF text empty, using filename")
                    if is_unhelpful_name(clean_name):
                        print(f"  ⏭️ SKIP - Empty PDF, no useful filename")
                        skipped_count += 1
                        continue
                    content = clean_name
                    is_filename_only = True
            except Exception as e:
                print(f"  ⚠️ Could not read PDF, using filename: {e}")
                if is_unhelpful_name(clean_name):
                    print(f"  ⏭️ SKIP - Unreadable PDF, no useful filename")
                    skipped_count += 1
                    continue
                content = clean_name
                is_filename_only = True
                
        elif ext_lower == ".epub":
            title = epub_to_title(filepath)
            if title:
                print(f"  📖 Found epub title: {title}")
                content = title
                is_filename_only = True
            else:
                if is_unhelpful_name(clean_name):
                    print(f"  ⏭️ SKIP - No epub title, no useful filename")
                    skipped_count += 1
                    continue
                content = clean_name
                is_filename_only = True
                
        elif ext_lower == ".docx":
            content = docx_to_text(filepath)
            if not content or len(content) < 50:
                print(f"  ⚠️ DOCX text insufficient, using filename")
                if is_unhelpful_name(clean_name):
                    print(f"  ⏭️ SKIP - No useful content or filename")
                    skipped_count += 1
                    continue
                content = clean_name
                is_filename_only = True
        else:
            if is_unhelpful_name(clean_name):
                print(f"  ⏭️ SKIP - No useful filename")
                skipped_count += 1
                continue
            content = clean_name
            is_filename_only = True

        try:
            new_name = get_new_filename_from_openai(content, is_filename_only, original_filename=filename)
            if is_unhelpful_name(new_name) and not is_filename_only:
                print(f"  🔄 AI returned unhelpful name, retrying with filename...")
                if is_unhelpful_name(clean_name):
                    print(f"  ⏭️ SKIP - No meaningful title found")
                    skipped_count += 1
                    continue
                new_name = get_new_filename_from_openai(clean_name, is_filename_only=True, original_filename=filename)
            if is_unhelpful_name(new_name):
                print(f"  ⏭️ SKIP - No meaningful title found")
                skipped_count += 1
                continue
        except Exception as e:
            print(f"  ❌ SKIP - API error: {e}")
            failed_count += 1
            continue

        new_filename = new_name + ext
        
        # Check if already correctly named
        if new_filename == filename or new_name.lower().replace(' ', '') == name.lower().replace(' ', ''):
            print(f"  ✓ Already named correctly")
            skipped_count += 1
            continue
            
        existing = os.listdir(directory)
        
        # Handle collisions with _01, _02 suffix
        if new_filename in existing:
            counter = 1
            while f"{new_name}_{counter:02d}{ext}" in existing:
                counter += 1
            new_filename = f"{new_name}_{counter:02d}{ext}"
            print(f"  ⚠️ Name collision, using: {new_filename}")

        new_filepath = os.path.join(directory, new_filename)
        try:
            os.rename(filepath, new_filepath)
            print(f"  ✅ RENAMED -> {new_filename}")
            renamed_count += 1
        except Exception as e:
            print(f"  ❌ Error renaming: {e}")
            failed_count += 1
    
    # Summary
    print(f"\n{'='*60}")
    print(f"📊 Summary: {renamed_count} renamed, {skipped_count} skipped, {failed_count} failed")
    print(f"{'='*60}")

def clean_path(path):
    path = path.strip().strip('"').strip("'")
    path = re.sub(r'\\(.)', r'\1', path)
    path = os.path.expanduser(path)
    return path

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="📚 PDFs-AI-Rename - Enhanced AI-powered document renamer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  riffo /path/to/books              Process all files in directory
  riffo ~/Downloads                 Process Downloads folder
  riffo .                           Process current directory
        """
    )
    parser.add_argument("path", nargs="?", help="Directory path to process")
    
    args = parser.parse_args()
    
    if args.path:
        directory = args.path
    else:
        directory = input("Please input your path: ")
    
    directory = clean_path(directory)
    if not os.path.isdir(directory):
        print(f"Error: '{directory}' is not a valid directory")
        return
    for dirpath, dirnames, filenames in os.walk(directory):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        print(f"\n{'='*60}")
        print(f"📁 {dirpath}")
        print(f"{'='*60}")
        rename_files_in_directory(dirpath)

if __name__ == "__main__":
    main()
