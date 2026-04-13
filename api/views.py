import os
from django.core.cache import cache
from rest_framework.decorators import api_view
from rest_framework.response import Response
from playwright.sync_api import sync_playwright

@api_view(['GET'])
def hello_world(request):
    return Response({"message": "Hello, world!"})

@api_view(['POST'])
def check_license_status(request):
    license_no = request.data.get('license_no')
    name = request.data.get('name', '')
    
    # 1. Check Cache first
    cache_key = f"license_{license_no}_{name.strip().replace(' ', '_')}"
    cached_result = cache.get(cache_key)
    if cached_result:
        return Response({
            "success": True,
            "cached": True,
            "results": cached_result
        })

    # Toggle headless mode (User manually set False for testing)
    headless = os.environ.get('HEADLESS_BROWSER', 'True').lower() == 'true'
    # headless = False
    
    if not license_no:
        return Response({"error": "license_no is required"}, status=400)
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            page = browser.new_page()
            
            # Use a modern user agent
            page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            })
            
            page.goto('https://dangtmo.dotm.gov.np/DrivingLicense/SearchLicense', timeout=60000, wait_until='load')
            
            # Wait for fields to be interactable
            page.wait_for_selector('#inputDLNO', timeout=30000)
            
            # Standardizing inputs: clear and type
            # Some sites have JS listeners, focus + keyboard.type is safer
            page.click('#inputDLNO')
            page.keyboard.press('Control+A')
            page.keyboard.press('Backspace')
            page.keyboard.type(str(license_no), delay=50)
            
            if name:
                page.click('#inputName')
                page.keyboard.press('Control+A')
                page.keyboard.press('Backspace')
                page.keyboard.type(str(name), delay=50)
            
            # Small pause before searching
            page.wait_for_timeout(1000)
            
            # Click search and wait for network to settle
            page.click('button.searchLicense')
            
            # Crucial: Wait for the result to change from 'Empty' or 'Loading' to actual data
            # We wait for EITHER a result row OR the explicit 'dataTables_empty' message
            try:
                # Wait for any row that is NOT the empty one if possible, or just any result
                page.wait_for_selector('#SearchLicense tr', timeout=20000)
                
                # If we see 'dataTables_empty', we should wait a bit longer in case it's a false positive 
                # (sometimes sites show empty while loading)
                empty_row = page.query_selector('.dataTables_empty')
                if empty_row:
                    page.wait_for_timeout(3000) # Give it 3 more seconds
                
                rows = page.query_selector_all('#SearchLicense tr')
                results = []
                
                for row in rows:
                    cells = row.query_selector_all('td')
                    # Skip the 'No records found' row
                    if len(cells) == 1 and 'dataTables_empty' in (cells[0].get_attribute('class') or ''):
                        continue
                        
                    if len(cells) >= 7:
                        content = [c.inner_text().strip() for c in cells]
                        results.append({
                            "sn": content[0],
                            "dl_no": content[1],
                            "name": content[2],
                            "type": content[3],
                            "category": content[4],
                            "dispatch_date": content[5],
                            "branch": content[6],
                            "remarks": content[7] if len(content) > 7 else ""
                        })
                
                browser.close()
                
                if not results:
                    return Response({
                        "success": False,
                        "message": "No records found on the site. Please verify the License Number and Name."
                    }, status=404)

                # 2. Store in Cache for 24 hours
                cache.set(cache_key, results, timeout=86400)

                return Response({
                    "success": True,
                    "search_params": {"license_no": license_no, "name": name},
                    "results": results
                })
                
            except Exception as e:
                browser.close()
                return Response({
                    "success": False,
                    "message": "The search timed out or the site layout changed.",
                    "details": str(e)
                }, status=404)
                
    except Exception as e:
        return Response({
            "error": "Failed to connect to license search service",
            "details": str(e)
        }, status=500)

try:
    import pytesseract
    from PIL import Image
    import cv2
    import numpy as np
except ImportError:
    pytesseract = None
    cv2 = None
    np = None

import base64

def preprocess_captcha_image(image_path):
    """
    Advanced preprocessing for captcha image OCR accuracy.
    Optimized for character recognition with noise removal and contrast enhancement.
    """
    if cv2 is None:
        return Image.open(image_path).convert('L')
    
    try:
        # Read image
        img = cv2.imread(image_path)
        if img is None:
            return Image.open(image_path).convert('L')
        
        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Step 1: Upscale image for better OCR (Tesseract works better on larger images)
        # Multiply size by 2x for better character recognition
        scale_factor = 2
        h, w = gray.shape
        gray = cv2.resize(gray, (w * scale_factor, h * scale_factor), interpolation=cv2.INTER_CUBIC)
        
        # Step 2: Denoise to remove noise while preserving text edges
        # Use morphological operations to clean up
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
        gray = cv2.morphologyEx(gray, cv2.MORPH_OPEN, kernel, iterations=1)
        
        # Step 3: Increase contrast using CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        
        # Step 4: Apply bilateral filter to reduce noise while keeping edges sharp
        filtered = cv2.bilateralFilter(enhanced, 9, 75, 75)
        
        # Step 5: Use adaptive thresholding (better for captchas than global thresholding)
        # This adapts to local image regions, better for varying brightness
        binary = cv2.adaptiveThreshold(filtered, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                       cv2.THRESH_BINARY, 11, 2)
        
        # Step 6: Additional morphological operations to clean text
        kernel_clean = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel_clean, iterations=1)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_clean, iterations=1)
        
        # Convert back to PIL Image for Tesseract
        return Image.fromarray(binary)
    except Exception as e:
        print(f"Preprocessing error: {e}. Using basic conversion.")
        try:
            return Image.open(image_path).convert('L')
        except:
            return None

def solve_captcha_with_ocr(image_path):
    """
    Advanced OCR solving with alphanumeric focus and multiple PSM strategies.
    Optimized for 4-8 character captchas.
    """
    if not pytesseract:
        return ""
    
    try:
        # Preprocess image
        img = preprocess_captcha_image(image_path)
        if img is None:
            return ""
        
        best_result = ""
        results_quality = []
        
        # Try Tesseract PSM modes optimized for captcha character recognition
        psm_modes = [
            (8, "single word"),           # Best for 4-8 character captchas
            (7, "text line"),             # Single line alternative
            (6, "text block"),            # Block of uniform text
            (13, "sparse text"),          # Scattered characters
        ]
        
        for psm, desc in psm_modes:
            try:
                # Use character whitelist to only recognize alphanumeric
                config = f"--psm {psm} -c tesseract_create_pdf=0 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
                text = pytesseract.image_to_string(img, config=config).strip()
                
                # Filter to alphanumeric only
                cleaned = ''.join(c for c in text if c.isalnum())
                
                # Captchas are typically 4-8 chars, sometimes up to 10
                if cleaned and 3 <= len(cleaned) <= 10:
                    results_quality.append((len(cleaned), cleaned, desc))
                    
            except Exception:
                continue
        
        # Choose best result: prefer by length (more chars = more confidence)
        if results_quality:
            results_quality.sort(reverse=True, key=lambda x: x[0])
            best_result = results_quality[0][1]
        
        # Fallback: confidence-based extraction
        if not best_result:
            try:
                config = "--psm 8 -c tesseract_create_pdf=0"
                text_data = pytesseract.image_to_data(img, config=config, output_type='dict')
                
                # Extract high-confidence characters (>40%)
                high_conf = []
                for i, conf in enumerate(text_data['conf']):
                    if int(conf) > 40 and text_data['text'][i].isalnum():
                        high_conf.append(text_data['text'][i])
                
                best_result = ''.join(high_conf).strip()
            except Exception:
                pass
        
        return best_result
    except Exception as e:
        print(f"OCR error: {e}")
        return ""

def find_captcha_image_selector(page):
    """
    Intelligently discover captcha image element on the page.
    Returns (selector_string, debug_info) or (None, debug_info)
    """
    debug_info = []
    
    # Strategy 1: Find by img with visible dimensions (skip logo at index 0)
    try:
        all_imgs = page.query_selector_all("img")
        if len(all_imgs) > 1:
            debug_info.append(f"ℹ Found {len(all_imgs)} images, analyzing...")
            # Skip first image (usually logo), check others
            for idx in range(1, len(all_imgs)):
                try:
                    img = all_imgs[idx]
                    box = img.bounding_box()
                    if box:
                        w = box.get('width', 0)
                        h = box.get('height', 0)
                        # Captcha typically 100-400px wide, 30-150px tall
                        if 100 < w < 400 and 30 < h < 150:
                            src = (img.get_attribute('src') or 'no-src')[:40]
                            debug_info.append(f"✓ Captcha img#{idx}: {w}x{h}px, src={src}")
                            # Return img selector at this position (will use .first for safety)
                            return f"img:nth-child({idx + 1})", debug_info
                except Exception:
                    pass
    except Exception as e:
        debug_info.append(f"ℹ Size analysis failed")
    
    # Strategy 2: Find by keyword attributes
    keyword_selectors = [
        ("img[src*='captcha' i]", "src='captcha'"),
        ("img[alt*='captcha' i]", "alt='captcha'"),
        ("img[class*='captcha' i]", "class='captcha'"),
    ]
    
    for selector, desc in keyword_selectors:
        try:
            if page.query_selector(selector):
                debug_info.append(f"✓ Found via {desc}")
                return selector, debug_info
        except Exception:
            pass
    
    # Strategy 3: Find by structure (near form inputs)
    structure_selectors = [
        ("input[placeholder*='CAPTCHA'] ~ img", "img after captcha input"),
        ("input[placeholder*='CAPTCHA'] + img", "img immediately after input"),
        ("label:has-text('CAPTCHA') ~ img", "img after CAPTCHA label"),
        (".form-group img", "img in form-group"),
        ("div.row img", "img in row div"),
    ]
    
    for selector, desc in structure_selectors:
        try:
            if page.query_selector(selector):
                debug_info.append(f"✓ Found via {desc}: {selector}")
                return selector, debug_info
        except Exception:
            pass
    
    # Strategy 4: Find by data attributes
    data_selectors = [
        ("img[data-type='captcha']", "data-type attribute"),
        ("img[class*='captcha' i]", "captcha in class name"),
        ("img[src*='captcha' i]", "captcha in src URL"),
    ]
    
    for selector, desc in data_selectors:
        try:
            if page.query_selector(selector):
                debug_info.append(f"✓ Found via {desc}: {selector}")
                return selector, debug_info
        except Exception:
            pass
    
    # Fallback: Use the largest image (often captcha)
    try:
        all_imgs = page.query_selector_all("img")
        if len(all_imgs) > 1:
            largest_idx = 0
            largest_area = 0
            for idx, img in enumerate(all_imgs):
                try:
                    box = img.bounding_box()
                    if box:
                        area = box.get('width', 0) * box.get('height', 0)
                        if area > largest_area and area < 500000:  # Not too huge (like banner)
                            largest_area = area
                            largest_idx = idx
                except Exception:
                    pass
            if largest_area > 1000:  # Must have minimum size
                debug_info.append(f"✓ Using largest image (#{largest_idx}) as fallback")
                return f"img:nth-of-type({largest_idx + 1})", debug_info
    except Exception as e:
        debug_info.append(f"✗ Fallback attempt failed: {e}")
    
    debug_info.append("✗ NO CAPTCHA IMAGE FOUND")
    return None, debug_info

@api_view(['POST'])
def get_captcha(request):
    """
    Step 1: Fill info and get captcha with intelligent OCR solving.
    Returns solved text if possible, and always a base64 image.
    """
    phone_number = request.data.get('phone_number', '9765153986')
    user_data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'browser_session_ppan')
    headless = os.environ.get('HEADLESS_BROWSER', 'True').lower() == 'true'
    
    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=headless,
                viewport={'width': 1280, 'height': 800}
            )
            page = context.pages[0] if context.pages else context.new_page()
            
            # Navigate to the registration page
            page.goto('http://ereturns.ird.gov.np:8289/registrationNew', timeout=60000, wait_until='networkidle')
            
            # Fill phone number
            page.wait_for_selector('input.form-control', timeout=10000)
            page.fill('input.form-control', str(phone_number))
            
            # Small delay to let page render
            page.wait_for_timeout(1000)
            
            # Capture full page screenshot for debugging
            debug_screenshot_path = os.path.join(os.path.dirname(user_data_dir), 'captcha_page_debug.png')
            page.screenshot(path=debug_screenshot_path)
            
            # Find captcha element intelligently
            captcha_selector, debug_messages = find_captcha_image_selector(page)
            
            captcha_path = os.path.join(os.path.dirname(user_data_dir), 'captcha_temp.png')
            captcha_found = False
            
            if captcha_selector:
                try:
                    # Use Locator API with .first to handle multiple matches (strict mode)
                    locator = page.locator(captcha_selector).first
                    locator.wait_for(state='visible', timeout=5000)
                    locator.screenshot(path=captcha_path)
                    debug_messages.append(f"✓ Screenshot captured successfully")
                    captcha_found = True
                except Exception as e:
                    debug_messages.append(f"✗ Screenshot failed: {str(e)[:80]}")
            
            # Determine which image to use
            if not captcha_found:
                captcha_path = debug_screenshot_path
                warning = " | ".join(debug_messages[-2:])  # Show last 2 debug messages
            else:
                warning = None
            
            # Encode image to base64
            with open(captcha_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            
            # Attempt advanced OCR
            solved_text = ""
            if pytesseract and captcha_found:
                try:
                    solved_text = solve_captcha_with_ocr(captcha_path)
                    if solved_text:
                        debug_messages.append(f"✓ OCR solved: {solved_text}")
                    else:
                        debug_messages.append(f"ℹ OCR returned empty result")
                except Exception as e:
                    debug_messages.append(f"✗ OCR error: {str(e)[:80]}")
            
            context.close()
            
            return Response({
                "success": True,
                "solved_text": solved_text,
                "captcha_image_base64": f"data:image/png;base64,{encoded_string}",
                "phone_number": phone_number,
                "warning": warning,
                "debug": debug_messages if not captcha_found else []
            })
            
    except Exception as e:
        return Response({"success": False, "error": str(e)}, status=500)

@api_view(['POST'])
def apply_ppan(request):
    """
    Step 2: Submit with the provided captcha.
    """
    captcha_text = request.data.get('captcha')
    phone_number = request.data.get('phone_number') # Usually already filled
    
    if not captcha_text:
        return Response({"error": "captcha is required"}, status=400)
        
    user_data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'browser_session_ppan')
    headless = os.environ.get('HEADLESS_BROWSER', 'True').lower() == 'true'
    
    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=headless
            )
            page = context.pages[0] if context.pages else context.new_page()
            
            # Re-navigate if session was lost, though persistent context should help
            if 'registrationNew' not in page.url:
                page.goto('http://ereturns.ird.gov.np:8289/registrationNew')
                if phone_number:
                    page.fill('input.form-control', str(phone_number))
            
            # Fill the captcha
            page.fill("input[placeholder='Enter CAPTCHA']", str(captcha_text))
            
            # Click Continue (Continue button is usually .btn-success or similar)
            # Identifying the button: Based on common IRD layout it might be "Continue" or "Submit"
            # We'll use a text selector for reliability
            page.click("text=Continue")
            
            # Wait for next step (e.g. OTP field or success message)
            page.wait_for_timeout(3000)
            
            screenshot_path = os.path.join(os.path.dirname(user_data_dir), 'ppan_after_submit.png')
            page.screenshot(path=screenshot_path)
            
            final_url = page.url
            context.close()
            
            return Response({
                "success": True,
                "message": "Form submitted. Check screenshot for status.",
                "current_url": final_url
            })
            
    except Exception as e:
        return Response({"success": False, "error": str(e)}, status=500)
