import cv2
import numpy as np
import pytesseract
import re
from PIL import Image
from io import BytesIO


# Nepali to English numeral conversion
NEPALI_DIGITS = {
    '०': '0', '१': '1', '२': '2', '३': '3', '४': '4',
    '५': '5', '६': '6', '७': '7', '८': '8', '९': '9'
}


def convert_nepali_to_english(text):
    """Convert Nepali numerals to English numerals - safely handles None"""
    if not text:
        return text
    result = str(text)
    for nepali, english in NEPALI_DIGITS.items():
        result = result.replace(nepali, english)
    return result


def safe_extract(match, group_num=1):
    """Safely extract and clean matched text - handles None gracefully"""
    try:
        if match and match.group(group_num):
            value = match.group(group_num)
            if value is not None:
                return str(value).strip()
    except (IndexError, AttributeError, TypeError):
        pass
    return None


def process_citizenship_image(image_file):
    """
    Process citizenship document image and extract text using OCR.
    Optimized for Nepali citizenship documents with improved preprocessing.
    
    Args:
        image_file: Django UploadedFile object
        
    Returns:
        dict: Extracted data from the citizenship document
    """
    
    # Read image from file
    pil_image = Image.open(image_file)
    img_array = np.array(pil_image)
    img = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
    
    # Step 1: Resize for better OCR (3x upscaling)
    img = cv2.resize(img, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    
    # Step 2: Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Step 3: Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
    # Better for documents with varying lighting/shadows
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    
    # Step 4: Apply bilateral filter to denoise while preserving edges
    denoised = cv2.bilateralFilter(gray, 9, 75, 75)
    
    # Step 5: Apply OTSU thresholding for binarization
    _, binary = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # Step 6: Morphological operations to clean up noise
    kernel_morph = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    morph = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel_morph, iterations=1)
    morph = cv2.morphologyEx(morph, cv2.MORPH_OPEN, kernel_morph, iterations=1)
    
    # Step 7: Sharpen the result
    kernel_sharp = np.array([[0, -1, 0],
                             [-1, 5, -1],
                             [0, -1, 0]])
    final = cv2.filter2D(morph, -1, kernel_sharp)
    
    # Step 8: Extract text using Tesseract OCR with optimized config
    # PSM 6: Assume a single uniform block of text
    # OEM 3: Use both legacy and LSTM OCR engine modes
    config = r'--oem 3 --psm 6 -c tessedit_char_whitelist='
    text = pytesseract.image_to_string(
        final,
        lang="nep+eng",
        config=config
    )
    
    # Parse and extract data
    data = parse_citizenship_text(text)
    data['raw_text'] = text
    
    return data


def parse_citizenship_text(text):
    """
    Parse OCR text and extract detailed citizenship information with error handling.
    
    Args:
        text: Raw OCR extracted text
        
    Returns:
        dict: Structured citizenship data with extracted fields
    """
    data = {}
    
    try:
        # Preliminary cleanup of common OCR artifacts
        text = re.sub(r'\bAl\.\s*Wate\b', '', text)  # Remove "Al. Wate:" artifact
        text = re.sub(r'\bWate\b', '', text)  # Remove standalone "Wate"
        text = re.sub(r'\bMsc\s*=', '', text)  # Remove "Msc ="
        text = re.sub(r'\|', '', text)  # Remove pipe artifacts
        text = re.sub(r'_', '', text)  # Remove underscore artifacts
        
        # Clean text (important) - preserve line breaks for better context
        clean_text = re.sub(r'\s+', ' ', text).strip()
        if not clean_text:
            return data
        
        # ============== PERSONAL INFORMATION ==============
        
        # Citizenship number - handle both formats (ना.प्र.नं and ना.प्र.न.) with OCR corruption
        # Pattern should match the full number with dashes/dots, not just single digit
        citizenship_patterns = [
            r'नागरिकता\s*नम्बर ?(?::;|:|=|-) ?([0-9\-०-९०-९\.]+)',  # At least 6 digits with dashes/dots
            r'ना[.्]?प्र[.्]?र?न[.्]?ं?[.्]? ?(?::;|:|=|-) ?([0-9.\-०-९०-९]{6,})',  # Corrupted variants, 6+ chars
            r'ना-प्र[\w\.]*? ?(?::;|:|=|-) ?([0-9.\-०-९०-९]{6,})',  # At least 6 digit groups
            r'citizenship\s*(?:no|number) ?(?::;|:|=|-) ?([0-9.\-०-९०-९]{6,})',
        ]
        for pattern in citizenship_patterns:
            match = re.search(pattern, clean_text, re.IGNORECASE)
            citizenship_no = safe_extract(match, 1)
            if citizenship_no:
                data["citizenship_no"] = convert_nepali_to_english(citizenship_no)
                break
        
        # Name - robust extraction that stops before gender/other labels
        # Use negative lookbehind to avoid spouse's name (पति/पत्नीको नामथर)
        name_patterns = [
            r'(?<!पति)(?<!पत्नी)(?<!spouse)\s*नाम\s*(?:थर|UT|[\w]*?)\s*[:=]+\s*(.+?)(?:\s+लिङ्ग|\s+gender|\s+sex|\s+Al\.|\s+Wate)',  
            r'(?<!पति)(?<!पत्नी)\s*नाम\s*[:=]+\s*([^:|]+?)(?=\s+(?:लिङ्ग|gender|sex|Al\.|Wate|ATLA))',  
            r'(?<!spouse)\s*नाम\s*(?:थर|UT)?\s*[:=]+\s*([^\n:;|]+?)(?=\s+:|$)',
        ]
        for pattern in name_patterns:
            match = re.search(pattern, clean_text, re.IGNORECASE)
            name = safe_extract(match, 1)
            if name and len(name.strip()) > 1:
                name = re.sub(r'\s+', ' ', name).strip()
                # Remove only the trailing keywords/artifacts
                name = re.sub(r'\s+(?:लिङ्ग|gender|sex|Al\..*|Wate.*)$', '', name, flags=re.IGNORECASE).strip()
                # Check if name contains any Nepali characters and not spouse info
                if name and len(name) > 1 and re.search(r'[\u0900-\u097F]', name) and 'ATLA' not in name:
                    data["name"] = name
                    break
        
        # First name
        match = re.search(r'(?:first\s*name|प्रथम\s*नाम) ?(?::|=)? ?([^\s:=\n]+)', clean_text, re.IGNORECASE)
        first_name = safe_extract(match, 1)
        if first_name:
            data["first_name"] = first_name
        
        # Last name - extract from the full name if available
        if "name" in data and data["name"]:
            # Get last Nepali word as surname
            name_parts = data["name"].strip().split()
            if len(name_parts) > 1:
                data["last_name"] = name_parts[-1]
            else:
                data["last_name"] = data["name"]
        else:
            # Fallback: search for explicit last name
            match = re.search(r'(?:last\s*name|surname|family\s*name) ?(?::|=)? ?([^\s\n:=]+)', clean_text, re.IGNORECASE)
            last_name = safe_extract(match, 1)
            if last_name:
                data["last_name"] = last_name
        
        # Gender - improved to handle inline with name
        gender_patterns = [
            r'(?:लिङ्ग|gender|sex)\s*[:=]+\s*([^\s\n:=|]+)',  # Standard format
            r'लिङ्ग\s*[:=]+\s*([^\n:=]+?)(?=\n|जन्म|birth|$)',  # Handle newlines
        ]
        for pattern in gender_patterns:
            match = re.search(pattern, clean_text, re.IGNORECASE)
            gender = safe_extract(match, 1)
            if gender:
                data["gender"] = gender
                if gender.lower() in ['m', 'male', 'पुरुष', 'म']:
                    data["gender_normalized"] = "Male"
                elif gender.lower() in ['f', 'female', 'महिला']:
                    data["gender_normalized"] = "Female"
                elif gender.lower() in ['o', 'other', 'अन्य']:
                    data["gender_normalized"] = "Other"
                break
        
        # ============== DATE OF BIRTH ==============
        # DOB with proper character class
        dob_patterns = [
            r'(?:जन्म\s*मिति|date\s*of\s*birth|dob) ?(?::|=)? ?([0-9०-९]+)[-/\.]?([0-9०-९]+)[-/\.]?([0-9०-९]+)',
            r'साल ?(?::|=)? ?([०-९0-9]+)[^\d०-९]*?महिना ?(?::|=)? ?([०-९0-9]+)[^\d०-९]*?गते? ?(?::|=)? ?([०-९0-9]+)',
            r'([0-9०-९]{4})[-/\.]([0-9०-९]{1,2})[-/\.]([0-9०-९]{1,2})',
        ]
        
        for pattern in dob_patterns:
            match = re.search(pattern, clean_text, re.IGNORECASE)
            if match:
                year = safe_extract(match, 1)
                month = safe_extract(match, 2)
                day = safe_extract(match, 3)
                if year and month and day:
                    year = convert_nepali_to_english(year)
                    month = convert_nepali_to_english(month).zfill(2)
                    day = convert_nepali_to_english(day).zfill(2)
                    data["dob"] = f"{year}-{month}-{day}"
                    break
        
        # Age
        match = re.search(r'(?:उमेर|age) ?(?::|=)? ?([0-9०-९]+)', clean_text, re.IGNORECASE)
        age = safe_extract(match, 1)
        if age:
            data["age"] = convert_nepali_to_english(age)
        
        # ============== ADDRESS INFORMATION ==============
        
        # District - prioritize "जिल्ला :" format to avoid capturing "प्रशासन"
        district_patterns = [
            r'जिल्ला\s*[:=]+\s*([^\s\n:=]+)',  # Match "जिल्ला : <value>"
            r'district\s*[:=]+\s*([^\s\n:=]+)',
            r'जिल्ला\s+(?:प्रशासन)?.*?जिल्ला\s*[:=]+\s*([^\s\n:=]+)',  # Skip "जिल्ला प्रशासन"
        ]
        for pattern in district_patterns:
            match = re.search(pattern, clean_text, re.IGNORECASE)
            district = safe_extract(match, 1)
            if district and district.lower() not in ['प्रशासन', 'administration', 'सन्त्रालय']:
                data["district"] = district
                break
        
        # Province
        match = re.search(r'(?:प्रदेश|province|state) ?(?::|=)? ?([^\s\n:=]+)', clean_text, re.IGNORECASE)
        province = safe_extract(match, 1)
        if province:
            data["province"] = province
        
        # Birth district
        match = re.search(r'जन्म\s*(?:स्थान)?[^\n]*?जिल्ला ?(?::|=)? ?([^\s\n:=]+)', clean_text, re.IGNORECASE)
        birth_district = safe_extract(match, 1)
        if birth_district:
            data["birth_district"] = birth_district
        
        # Municipality/City
        municipalities = [
            'काठमाडौं', 'Kathmandu', 'काठमडौँ',
            'भक्तपुर', 'Bhaktapur',
            'ललितपुर', 'Lalitpur', 'पाताने',
            'हेटौडा', 'हेटौँडा', 'Hetauda',
            'पोखरा', 'Pokhara', 'पोखरा',
            'बिराटनगर', 'Biratnagar',
            'जनकपुरधाम', 'Janakpur',
            'नेपालगञ्ज', 'Nepalgunj',
            'बीरगञ्ज', 'Birgunj', 'बीरगुञ्ज',
            'दमक', 'Damak',
        ]
        
        for municipality in municipalities:
            if municipality in clean_text:
                data["municipality"] = municipality
                break
        
        # Alternative municipality pattern
        if "municipality" not in data:
            match = re.search(r'(?:नगरपालिका|municipality|city) ?(?::|=)? ?([^\s\n:=]+)', clean_text, re.IGNORECASE)
            muni = safe_extract(match, 1)
            if muni:
                data["municipality"] = muni
        
        # Ward number (fixed character class)
        ward_patterns = [
            r'वडा\s*नं\.? ?(?::|=)? ?([0-9०-९]+)',
            r'ward\s*(?:no\.?|number)? ?(?::|=)? ?([0-9०-९]+)',
            r'वडा ?(?::|=)? ?([0-9०-९]+)',
        ]
        for pattern in ward_patterns:
            match = re.search(pattern, clean_text, re.IGNORECASE)
            ward = safe_extract(match, 1)
            if ward:
                data["ward"] = convert_nepali_to_english(ward)
                break
        
        # VDC/Village area
        vdc_patterns = [
            r'गा\.वि\. ?[^\s:]* ?(?::|=)? ?([^\s\n:=]+)',
            r'(?:गा\.वि\.स|vdc|village) ?(?::|=)? ?([^\s\n:=]+)',
        ]
        for pattern in vdc_patterns:
            match = re.search(pattern, clean_text, re.IGNORECASE)
            vdc = safe_extract(match, 1)
            if vdc:
                data["vdc_area"] = vdc
                break
        
        # Full address
        match = re.search(r'(?:ठेगाना|address) ?(?::|=)? ?([^\n:=]+)', clean_text, re.IGNORECASE)
        full_address = safe_extract(match, 1)
        if full_address:
            data["full_address"] = full_address
        
        # Street/Tole
        match = re.search(r'(?:टोल|street|tole) ?(?::|=)? ?([^\n:=]+)', clean_text, re.IGNORECASE)
        street = safe_extract(match, 1)
        if street:
            data["street"] = street
        
        # ============== FAMILY INFORMATION ==============
        
        # Father - using lenient approach to find names with नाप्ने suffix
        # Look for patterns with common surnames followed by "नाप्ने"
        father = None
        # Pattern 1: Explicit father keyword
        match = re.search(r'(?:पिता|father)\s*[:=]?\s*(?:नाम\s*थर)?[:=]?\s*([^\n:]+?)(?=\n|आमा|माता|mother|नाप्ने|ना\.कि)', clean_text, re.IGNORECASE)
        if match:
            father = safe_extract(match, 1)
        
        # Pattern 2: Name with surname + "नाप्ने" marker (first occurrence)
        if not father:
            match = re.search(r'((?:[\u0900-\u097F]+\s+)*(?:[\u0900-\u097F]+\s+)?(?:थिङ|शर्मा|गुप्ता|पाण्डे|भट्टराई|शाह|वरिष्ठ|नेपाली))\s+नाप्ने', clean_text)
            if match:
                father = safe_extract(match, 1)
        
        if father:
            father = re.sub(r'\s+', ' ', father).strip()
            # Remove trailing artifacts
            father = re.sub(r'\.+.*$|नाप्ने.*$|ना\.कि.*$|नान.*$|\d+\.$|^\d+\s+|^[\d०-९]+\s+', '', father, flags=re.IGNORECASE).strip()
            # Validate it's a name and not garbage
            if father and 5 < len(father) < 100 and father.lower() not in ['xxx', 'none'] and re.search(r'[\u0900-\u097F]', father):
                # Skip if contains too much English text (header noise)
                if not re.search(r'[a-z]{5,}|सरकार|मन्त्रालय', father, re.IGNORECASE):
                    data["father"] = father
        
        # Mother - improved patterns with more lenient matching for OCR artifacts
        mother_patterns = [
            r'(?:आमा|माता|mother|M\.\s*NAME|MOTHER)\s*[:=]?\s*(?:नाम\s*थर)?[:=]?\s*([^\n:]+?)(?=\n|दादा|दादी|grandfather|grandmother|नाप्ने|ना\.कि|पति|$)',
            r'(?:आमा|माता|mother)[:=]*\s*([^\n:=|]+?)(?=\n|दादा|दादी|नाप्ने|पति)',
            r'नाम\s*थर[ः:]?\s*([^\n:]+?)(?=नाप्ने|ना\.कि|$)',  # "नाम थर:" before mother's name (corrupted format)
        ]
        for pattern in mother_patterns:
            match = re.search(pattern, clean_text, re.IGNORECASE)
            mother = safe_extract(match, 1)
            if mother:
                mother = re.sub(r'\s+', ' ', mother).strip()
                # Remove trailing artifacts
                mother = re.sub(r'\.+.*$|नाप्ने.*$|ना\.कि.*$|नान.*$|नु$|\d+\.$', '', mother, flags=re.IGNORECASE).strip()
                # Ensure it's not the main person's name and has Nepali text
                if mother and len(mother) > 2 and mother.lower() not in ['xxx', 'none'] and mother != data.get('name'):
                    if re.search(r'[\u0900-\u097F]', mother):
                        data["mother"] = mother
                        break
        
        # Grandfather
        match = re.search(r'(?:दादा|grandfather) ?(?::|=)? ?([^\n:=]+?)(?=दादी|grandmother|$)', clean_text, re.IGNORECASE)
        grandfather = safe_extract(match, 1)
        if grandfather and len(grandfather) > 2:
            data["grandfather"] = grandfather
        
        # Grandmother
        match = re.search(r'(?:दादी|grandmother) ?(?::|=)? ?([^\n:=]+?)(?=$)', clean_text, re.IGNORECASE)
        grandmother = safe_extract(match, 1)
        if grandmother and len(grandmother) > 2:
            data["grandmother"] = grandmother
        
        # ============== DOCUMENT INFORMATION ==============
        
        # Issue office - improved patterns for real-world OCR
        office_patterns = [
            r'जिल्ला\s*प्रशासन\s*कार्यालय\s*([^\n:=]+?)(?=\n|\.\.|$)',  # Extract location after "जिल्ला प्रशासन कार्यालय"
            r'(?:जिल्ला\s*)?(?:प्रशासन|प्रश)(?:\s*कार्यालय)?[:\s=]*([^\n:=]+?)(?=नाम|ना\.प्र|मिति|date|$)',
            r'(?:जारीकर्ता|issuing\s*office|issued\s*by)[:\s=]+([^\n:=]+?)(?=मिति|date|$)',
        ]
        for pattern in office_patterns:
            match = re.search(pattern, clean_text, re.IGNORECASE)
            office = safe_extract(match, 1)
            if office:
                office = re.sub(r'\s+', ' ', office).strip()
                # Clean up artifacts and prevent capturing citizenship numbers
                if not re.match(r'^[0-9\-०-९]+$', office):  # Skip if it's just numbers
                    office = re.sub(r'^कार्यालय\s*|are\s*be.*$|aT\s*Toate.*$|नान.*$|\.\..*$', '', office, flags=re.IGNORECASE).strip()
                    if office and len(office) > 1 and not re.match(r'^[0-9\-०-९]+$', office):
                        data["office"] = office
                        break
        
        # Issue date
        match = re.search(r'(?:जारी\s*मिति|issued\s*date|issue\s*date) ?(?::|=)? ?([0-9०-९\-/\.\s]+)', clean_text, re.IGNORECASE)
        issue_date = safe_extract(match, 1)
        if issue_date:
            data["issue_date"] = convert_nepali_to_english(issue_date.strip())
        
        # Expiry date
        match = re.search(r'(?:म्याद|expiry|expire|validity) ?(?::|=)? ?([0-9०-९\-/\.\s]+)', clean_text, re.IGNORECASE)
        expiry_date = safe_extract(match, 1)
        if expiry_date:
            data["expiry_date"] = convert_nepali_to_english(expiry_date.strip())
        
        # Document type
        if "ना.प्र.नं" in clean_text or "ना.प्र.नम्" in clean_text or "citizenship" in clean_text.lower():
            data["document_type"] = "Citizenship Certificate"
        
        # Registration number - be more specific to avoid spurious matches
        # Only extract if it looks like a number or from explicit registration field
        match = re.search(r'(?:पञ्जीकरण|registration|नागरिकता\s*दर्ता)[:\s=]+([0-9\-०-९]{5,})', clean_text, re.IGNORECASE)
        registration_no = safe_extract(match, 1)
        if registration_no and len(registration_no) > 2:
            data["registration_no"] = convert_nepali_to_english(registration_no)
        
        # ============== ADDITIONAL INFORMATION ==============
        
        # Occupation
        match = re.search(r'(?:पेशा|occupation|job) ?(?::|=)? ?([^\n:=]+)', clean_text, re.IGNORECASE)
        occupation = safe_extract(match, 1)
        if occupation:
            data["occupation"] = occupation
        
        # Marital status
        match = re.search(r'(?:विवाह\s*स्थिति|marital\s*status) ?(?::|=)? ?([^\s\n:=]+)', clean_text, re.IGNORECASE)
        marital_status = safe_extract(match, 1)
        if marital_status:
            data["marital_status"] = marital_status
        
        # Citizenship type
        match = re.search(r'(?:नागरिकता\s*प्रकार|citizenship\s*type) ?(?::|=)? ?([^\n:=]+)', clean_text, re.IGNORECASE)
        citizenship_type = safe_extract(match, 1)
        if citizenship_type:
            data["citizenship_type"] = citizenship_type
        
        # Blood group
        match = re.search(r'(?:रक्त\s*समूह|blood\s*group|blood\s*type) ?(?::|=)? ?([^\s\n:=]+)', clean_text, re.IGNORECASE)
        blood_group = safe_extract(match, 1)
        if blood_group:
            data["blood_group"] = blood_group
        
        # Mobile
        match = re.search(r'(?:मोबाइल|mobile|phone) ?(?::|=)? ?([0-9\-\+]+)', clean_text, re.IGNORECASE)
        mobile = safe_extract(match, 1)
        if mobile:
            data["mobile"] = mobile
        
        # Email
        match = re.search(r'(?:ईमेल|email) ?(?::|=)? ?([^\s\n:=]+@[^\s\n:=]+)', clean_text, re.IGNORECASE)
        email = safe_extract(match, 1)
        if email:
            data["email"] = email
        
        # Citizenship issued at
        match = re.search(r'(?:नागरिकता\s*जारी|citizenship\s*issued\s*at) ?(?::|=)? ?([^\n:=]+)', clean_text, re.IGNORECASE)
        citizenship_issued_at = safe_extract(match, 1)
        if citizenship_issued_at:
            data["citizenship_issued_at"] = citizenship_issued_at
        
        # Detection flags
        if "हस्ताक्षर" in clean_text or "signature" in clean_text.lower():
            data["has_signature"] = True
        
        if "फोटो" in clean_text or "photo" in clean_text.lower():
            data["has_photo"] = True
        
        if "औंठोको छाप" in clean_text or "thumb" in clean_text.lower():
            data["has_thumbprint"] = True
        
    except Exception as e:
        # Log error but don't crash - return what we have
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error parsing citizenship text: {str(e)}")
    
    return data
