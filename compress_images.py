from PIL import Image
import os
import io

def compress_image(filepath):
    """
    Compress image to max 800px width and 80% quality
    """
    try:
        # Open the image
        img = Image.open(filepath)
        
        # Convert to RGB if needed (for PNG with transparency)
        if img.mode in ('RGBA', 'LA'):
            img = img.convert('RGB')
        
        # Get original size
        original_size = os.path.getsize(filepath)
        
        # Resize to max 800px width (maintain aspect ratio)
        max_width = 800
        if img.width > max_width:
            ratio = max_width / img.width
            new_size = (max_width, int(img.height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        
        # Save with compression
        img.save(filepath, optimize=True, quality=80)
        
        # Get new size
        new_size = os.path.getsize(filepath)
        
        print(f"✅ Compressed: {os.path.basename(filepath)} ({original_size//1024}KB → {new_size//1024}KB)")
        return True
    except Exception as e:
        print(f"❌ Compression failed for {filepath}: {e}")
        return False

def compress_images_in_folder(folder_path):
    """
    Compress all images in a folder (for existing images)
    """
    compressed = 0
    for filename in os.listdir(folder_path):
        if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
            filepath = os.path.join(folder_path, filename)
            if compress_image(filepath):
                compressed += 1
    print(f"✅ Compressed {compressed} images in {folder_path}")
    return compressed

def create_thumbnail(filepath, size=(200, 200)):
    """
    Create a thumbnail version of an image (for listing pages)
    """
    try:
        img = Image.open(filepath)
        img.thumbnail(size, Image.Resampling.LANCZOS)
        
        # Save as thumbnail
        base, ext = os.path.splitext(filepath)
        thumb_path = f"{base}_thumb{ext}"
        img.save(thumb_path, optimize=True, quality=70)
        return thumb_path
    except Exception as e:
        print(f"❌ Thumbnail creation failed: {e}")
        return None
