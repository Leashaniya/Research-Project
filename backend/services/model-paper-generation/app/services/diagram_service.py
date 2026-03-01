
import requests
import base64
import zlib
from pathlib import Path
import time

class DiagramService:
    """
    Service to convert Mermaid code into images using Kroki.io.
    """
    
    @staticmethod
    def _encode_mermaid(mermaid_code: str) -> str:
        """
        Encodes Mermaid code for Kroki (Deflate + Base64Url).
        """
        # 1. Encode to utf-8
        utf8_bytes = mermaid_code.encode('utf-8')
        
        # 2. Compress using zlib (Deflate)
        # Verify if window_bits is correct for standard deflate
        compressed = zlib.compress(utf8_bytes, level=9)
        
        # 3. Base64 URL safe encoding
        # Note: zlib.compress result includes header/checksum, but Kroki expects raw deflate?
        # Let's check Kroki python example logic:
        # base64.urlsafe_b64encode(zlib.compress(mermaid_code.encode('utf-8'), 9)).decode('utf-8')
        # This is the standard way.
        
        encoded = base64.urlsafe_b64encode(compressed).decode('utf-8')
        return encoded

    @staticmethod
    def render_mermaid_to_image(mermaid_code: str, output_path: str, format: str = "png") -> bool:
        """
        Renders mermaid code to an image file.
        params:
            mermaid_code: The raw mermaid syntax string.
            output_path: Absolute path to save the image.
            format: 'png' or 'svg'.
        """
        if not mermaid_code or not mermaid_code.strip():
            print("❌ DiagramService: Empty mermaid code provided.")
            return False
            
        try:
            # Kroki API URL
            # https://kroki.io/mermaid/{format}/{encoded_string}
            
            encoded_code = DiagramService._encode_mermaid(mermaid_code)
            url = f"https://kroki.io/mermaid/{format}/{encoded_code}"
            
            # Request
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                # Save to file
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                mode = "wb" if format == "png" else "w"
                encoding = None if format == "png" else "utf-8"
                
                with open(output_path, mode, encoding=encoding) as f:
                    # Write bytes for PNG, string for SVG (though response.content is bytes)
                    # For SVG, response.text is better. For PNG, response.content.
                    if format == "png":
                        f.write(response.content)
                    else:
                        f.write(response.text)
                        
                print(f"✅ Diagram saved to: {output_path}")
                return True
            else:
                print(f"❌ Kroki API failed: {response.status_code} - {response.text[:100]}")
                return False
                
        except Exception as e:
            print(f"❌ Diagram rendering failed: {e}")
            return False
