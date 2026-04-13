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
    """Convert Nepali numerals to English numerals"""
    if not text:
        return text
    result = str(text)
    for nepali, english in NEPALI_DIGITS.items():
        result = result.replace(nepali, english)
    return result


def safe_extract(match, group_num=1):
    """Safely extract and clean matched text"""
    try:
        if match and match.group(group_num):
            return match.group(group_num).strip()
    except (IndexError, AttributeError):
        pass
    return None


def process_citizenship_image(image_file):
    """
    Process citizenship document image and extract text using OCR.
    
    Args:
        image_file: Django UploadedFile object
        
    Returns:
        dict: Extracted data from the citizenship document
    """
    
    # Read image from file
    pil_image = Image.open(image_file)
    img_array = np.array(pil_image)
    img = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
    
    # Image preprocessing
    img = cv2.resize(img, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    
    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    
    # Sharpen the image
    kernel = np.array([[0, -1, 0],
                       [-1, 5, -1],
                       [0, -1, 0]])
    sharp = cv2.filter2D(gray, -1, kernel)
    
    # Extract text using Tesseract OCR
    config = r'--oem 3 --psm 4'
    text = pytesseract.image_to_string(
        sharp,
        lang="nep+eng",
        config=config
    )
    
    # Parse and extract data
    data = parse_citizenship_text(text)
    data['raw_text'] = text
    
    return data


def parse_citizenship_text(text):
    """
    Parse OCR text and extract detailed citizenship information.
    
    Args:
        text: Raw OCR extracted text
        
    Returns:
        dict: Structured citizenship data with extracted fields
    """
    data = {}
    
    # Clean text (important)
    clean_text = re.sub(r'\s+', ' ', text)
    
    # ============== PERSONAL INFORMATION ==============
    
    # Citizenship number - Multiple patterns for variations
    match = re.search(r'ना\.प्र\.नं\.? ?(?::|=)? ?([0-9\-०-९]+)', clean_text, re.IGNORECASE)
    if match:
        citizenship_no = convert_nepali_to_english(match.group(1).strip())
        data["citizenship_no"] = citizenship_no
    
    # Name (First name + Last name/Surname)
    match = re.search(r'नाम(?:थर)? ?(?::|=)? ?([^\n]+?)(?:लिङ्ग|gender|性別|$)', clean_text, re.IGNORECASE)
    if match:
        name = match.group(1).strip()
        name = re.sub(r'\s+', ' ', name).strip()
        data["name"] = name
    
    # First name specifically
    match = re.search(r'first\s*name|प्रथम\s*नाम ?(?::|=)? ?([^\s]+)', clean_text, re.IGNORECASE)
    if match:
        data["first_name"] = match.group(1).strip()
    
    # Last name/Surname
    match = re.search(r'(?:last\s*name|surname|थर|family\s*name) ?(?::|=)? ?([^\s\n]+)', clean_text, re.IGNORECASE)
    if match:
        data["last_name"] = match.group(1).strip()
    
    # Gender with multiple patterns
    gender_match = re.search(r'लिङ्ग|gender|sex|性別 ?(?::|=)? ?([^\s\n]+)', clean_text, re.IGNORECASE)
    if gender_match:
        gender = gender_match.group(1).strip()
        data["gender"] = gender
        if gender.lower() in ['m', 'male', 'पुरुष', 'म']:
            data["gender_normalized"] = "Male"
        elif gender.lower() in ['f', 'female', 'महिला', 'म्']:
            data["gender_normalized"] = "Female"
        elif gender.lower() in ['o', 'other', 'अन्य']:
            data["gender_normalized"] = "Other"
    
    # ============== DATE OF BIRTH ==============
    
    dob_patterns = [
        r'(?:जन्म\s*मिति|date\s*of\s*birth|dob) ?(?::|=)? ?(\d{4}|०-९+)-?(\d{2}|०-९+)-?(\d{2}|०-९+)',
        r'साल ?(?::|=)? ?([०-९0-9]+).*?महिना ?(?::|=)? ?([०-९0-9]+).*?गते? ?(?::|=)? ?([०-९0-9]+)',
        r'(\d{4}|[०-९]+)\s*[-/\.]\s*(\d{2}|[०-९]+)\s*[-/\.]\s*(\d{2}|[०-९]+)',
    ]
    
    for pattern in dob_patterns:
        match = re.search(pattern, clean_text, re.IGNORECASE)
        if match:
            year = convert_nepali_to_english(match.group(1).strip())
            month = convert_nepali_to_english(match.group(2).strip()).zfill(2)
            day = convert_nepali_to_english(match.group(3).strip()).zfill(2)
            data["dob"] = f"{year}-{month}-{day}"
            break
    
    age_match = re.search(r'(?:उमेर|age) ?(?::|=)? ?([0-9]+)', clean_text, re.IGNORECASE)
    if age_match:
        data["age"] = convert_nepali_to_english(age_match.group(1))
    
    # ============== ADDRESS INFORMATION ==============
    
    district_patterns = [
        r'जिल्ला ?(?::|=)? ?([^\s\n]+)',
        r'district ?(?::|=)? ?([^\s\n]+)',
    ]
    
    for pattern in district_patterns:
        match = re.search(pattern, clean_text, re.IGNORECASE)
        if match:
            district = match.group(1).strip()
            data["district"] = district
            break
    
    match = re.search(r'(?:प्रदेश|province|state) ?(?::|=)? ?([^\s\n]+)', clean_text, re.IGNORECASE)
    if match:
        data["province"] = match.group(1).strip()
    
    match = re.search(r'जन्म\s*(?:स्थान|जिल्ला)?.*?जिल्ला ?(?::|=)? ?([^\s\n]+)', clean_text, re.IGNORECASE)
    if match:
        data["birth_district"] = match.group(1).strip()
    
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
    
    muni_match = re.search(r'(?:नगरपालिका|municipality|city) ?(?::|=)? ?([^\s\n]+)', clean_text, re.IGNORECASE)
    if muni_match and "municipality" not in data:
        data["municipality"] = muni_match.group(1).strip()
    
    ward_patterns = [
        r'वडा\s*नं\.? ?(?::|=)? ?([0-9०-९]+)',
        r'ward\s*(?:no\.?|number)? ?(?::|=)? ?([0-9०-९]+)',
        r'वडा ?(?::|=)? ?([0-9०-९]+)',
    ]
    
    for pattern in ward_patterns:
        match = re.search(pattern, clean_text, re.IGNORECASE)
        if match:
            ward = convert_nepali_to_english(match.group(1).strip())
            data["ward"] = ward
            break
    
    vdc_patterns = [
        r'गा\.वि\. ?[^\s:]* ?(?::|=)? ?([^\s\n]+)',
        r'(?:गा\.वि\.स|vdc|village) ?(?::|=)? ?([^\s\n]+)',
    ]
    
    for pattern in vdc_patterns:
        match = re.search(pattern, clean_text, re.IGNORECASE)
        if match:
            vdc = match.group(1).strip()
            data["vdc_area"] = vdc
            break
    
    match = re.search(r'(?:ठेगाना|address) ?(?::|=)? ?([^\n]+)', clean_text, re.IGNORECASE)
    if match:
        data["full_address"] = match.group(1).strip()
    
    match = re.search(r'(?:टोल|street|tole) ?(?::|=)? ?([^\n]+)', clean_text, re.IGNORECASE)
    if match:
        data["street"] = match.group(1).strip()
    
    # ============== FAMILY INFORMATION ==============
    
    father_patterns = [
        r'(?:पिता|father|father\'s\s*name) ?(?::|=)? ?([^\n]+?)(?:आमा|mother|माता|$)',
        r'पिता\s*(.+?)(?:आमा|$)',
    ]
    
    for pattern in father_patterns:
        match = re.search(pattern, clean_text, re.IGNORECASE)
        if match:
            father = match.group(1).strip()
            father = re.sub(r'\s*[:=].*', '', father).strip()
            if father and len(father) > 2:
                data["father"] = father
                break
    
    mother_patterns = [
        r'(?:आमा|माता|mother|mother\'s\s*name) ?(?::|=)? ?([^\n]+?)(?:दादा|grandfather|$)',
        r'आमा\s*(.+?)(?:दादा|$)',
    ]
    
    for pattern in mother_patterns:
        match = re.search(pattern, clean_text, re.IGNORECASE)
        if match:
            mother = match.group(1).strip()
            mother = re.sub(r'\s*[:=].*', '', mother).strip()
            if mother and len(mother) > 2:
                data["mother"] = mother
                break
    
    match = re.search(r'(?:दादा|grandfather) ?(?::|=)? ?([^\n]+?)(?:दादी|grandmother|$)', clean_text, re.IGNORECASE)
    if match:
        data["grandfather"] = match.group(1).strip()
    
    match = re.search(r'(?:दादी|grandmother) ?(?::|=)? ?([^\n]+?)(?:$)', clean_text, re.IGNORECASE)
    if match:
        data["grandmother"] = match.group(1).strip()
    
    # ============== DOCUMENT INFORMATION ==============
    
    office_patterns = [
        r'(?:जिल्ला\s*प्रशासन|district\s*administration|issued\s*by) ?(?::|=)? ?([^\n]+?)(?:मिति|date|$)',
        r'(?:जारीकर्ता|issuing\s*office) ?(?::|=)? ?([^\n]+)',
    ]
    
    for pattern in office_patterns:
        match = re.search(pattern, clean_text, re.IGNORECASE)
        if match:
            office = match.group(1).strip()
            data["office"] = office
            break
    
    issue_date_patterns = [
        r'(?:जारी\s*मिति|issued\s*date|issue\s*date) ?(?::|=)? ?([0-9०-९\-/\.]+)',
    ]
    
    for pattern in issue_date_patterns:
        match = re.search(pattern, clean_text, re.IGNORECASE)
        if match:
            issue_date = match.group(1).strip()
            data["issue_date"] = convert_nepali_to_english(issue_date)
            break
    
    expiry_patterns = [
        r'(?:म्याद|expiry|expire|validity) ?(?::|=)? ?([0-9०-९\-/\.]+)',
    ]
    
    for pattern in expiry_patterns:
        match = re.search(pattern, clean_text, re.IGNORECASE)
        if match:
            expiry_date = match.group(1).strip()
            data["expiry_date"] = convert_nepali_to_english(expiry_date)
            break
    
    if "ना.प्र.नं" in clean_text or "citizenship" in clean_text.lower():
        data["document_type"] = "Citizenship Certificate"
    
    match = re.search(r'(?:रजिस्ट्रेसन|registration|reg\.?|id) ?(?::|=)? ?([^\s\n]+)', clean_text, re.IGNORECASE)
    if match:
        data["registration_no"] = match.group(1).strip()
    
    # ============== ADDITIONAL INFORMATION ==============
    
    match = re.search(r'(?:पेशा|occupation|job) ?(?::|=)? ?([^\n]+)', clean_text, re.IGNORECASE)
    if match:
        data["occupation"] = match.group(1).strip()
    
    match = re.search(r'(?:विवाह\s*स्थिति|marital\s*status) ?(?::|=)? ?([^\s\n]+)', clean_text, re.IGNORECASE)
    if match:
        status = match.group(1).strip()
        data["marital_status"] = status
    
    match = re.search(r'(?:नागरिकता\s*प्रकार|citizenship\s*type) ?(?::|=)? ?([^\n]+)', clean_text, re.IGNORECASE)
    if match:
        data["citizenship_type"] = match.group(1).strip()
    
    match = re.search(r'(?:रक्त\s*समूह|blood\s*group|blood\s*type) ?(?::|=)? ?([^\s\n]+)', clean_text, re.IGNORECASE)
    if match:
        data["blood_group"] = match.group(1).strip()
    
    match = re.search(r'(?:मोबाइल|mobile|phone) ?(?::|=)? ?([0-9\-\+]+)', clean_text, re.IGNORECASE)
    if match:
        data["mobile"] = match.group(1).strip()
    
    match = re.search(r'(?:ईमेल|email) ?(?::|=)? ?([^\s\n]+@[^\s\n]+)', clean_text, re.IGNORECASE)
    if match:
        data["email"] = match.group(1).strip()
    
    match = re.search(r'(?:नागरिकता\s*जारी|citizenship\s*issued\s*at) ?(?::|=)? ?([^\n]+)', clean_text, re.IGNORECASE)
    if match:
        data["citizenship_issued_at"] = match.group(1).strip()
    
    if "हस्ताक्षर" in clean_text or "signature" in clean_text.lower():
        data["has_signature"] = True
    
    if "फोटो" in clean_text or "photo" in clean_text.lower():
        data["has_photo"] = True
    
    if "औंठोको छाप" in clean_text or "thumb" in clean_text.lower():
        data["has_thumbprint"] = True
    
    return data
