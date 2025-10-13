#!/usr/bin/env python3
"""
Test document processing with real vessel data
"""

import requests
import json

def test_document_processing():
    """Test the document processing endpoint"""
    
    print("=== Testing Document Processing ===")
    
    # Test data
    template_name = "Sample_Vessel_Document.docx"
    vessel_imo = "IMO2379622"  # This should exist in the database
    
    print(f"Template: {template_name}")
    print(f"Vessel IMO: {vessel_imo}")
    
    # Create a dummy file
    dummy_file_path = "dummy.txt"
    with open(dummy_file_path, 'w') as f:
        f.write("dummy content")
    
    try:
        # Test the endpoint
        url = "http://localhost:8000/process-document"
        
        # Prepare form data
        files = {
            'template_file': ('dummy.txt', open(dummy_file_path, 'rb'), 'text/plain')
        }
        
        data = {
            'template_name': template_name,
            'vessel_imo': vessel_imo
        }
        
        print(f"\nSending request to: {url}")
        print(f"Data: {data}")
        
        # Send the request
        response = requests.post(url, files=files, data=data)
        
        print(f"\nResponse Status: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            # Check if it's a PDF
            content_type = response.headers.get('content-type', '')
            if 'application/pdf' in content_type:
                print("SUCCESS: PDF generated successfully!")
                print(f"PDF size: {len(response.content)} bytes")
                
                # Save the PDF for inspection
                with open('test_output.pdf', 'wb') as f:
                    f.write(response.content)
                print("PDF saved as 'test_output.pdf'")
            else:
                print("Response content:", response.text)
        else:
            print(f"ERROR: {response.status_code}")
            print(f"Error response: {response.text}")
            
    except Exception as e:
        print(f"EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean up
        try:
            import os
            if os.path.exists(dummy_file_path):
                os.remove(dummy_file_path)
        except:
            pass

if __name__ == "__main__":
    test_document_processing()
