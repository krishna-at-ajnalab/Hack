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
except ImportError:
    pytesseract = None

import base64

@api_view(['POST'])
def get_captcha(request):
    """
    Step 1: Fill info and get captcha.
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
            page.goto('http://ereturns.ird.gov.np:8289/registrationNew', timeout=60000)
            
            # Fill phone number
            page.wait_for_selector('input.form-control', timeout=10000)
            page.fill('input.form-control', str(phone_number))
            
            # Capture captcha image
            captcha_img = page.locator("div.col-md-4 img").first
            captcha_path = os.path.join(os.path.dirname(user_data_dir), 'captcha_temp.png')
            captcha_img.screenshot(path=captcha_path)
            
            # Encode image to base64
            with open(captcha_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            
            # Attempt OCR
            solved_text = ""
            if pytesseract:
                try:
                    img = Image.open(captcha_path).convert('L')
                    solved_text = pytesseract.image_to_string(img).strip()
                except Exception:
                    pass
            
            context.close()
            
            return Response({
                "success": True,
                "solved_text": solved_text,
                "captcha_image_base64": f"data:image/png;base64,{encoded_string}",
                "phone_number": phone_number
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
