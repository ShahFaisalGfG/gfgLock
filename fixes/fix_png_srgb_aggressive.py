#!/usr/bin/env python
"""Script to fix libpng sRGB warnings by completely stripping ICC profiles from PNG files."""

import os
from pathlib import Path
from PIL import Image

def fix_png_srgb_aggressive(file_path):
    """Fix sRGB profile in PNG file by stripping all color profiles."""
    try:
        # Load the PNG file
        img = Image.open(file_path)
        
        # Store original mode and transparency info
        original_mode = img.mode
        transparency = img.info.get('transparency', None)
        has_icc = 'icc_profile' in img.info
        
        # Convert to appropriate format
        if original_mode == 'RGBA':
            # Keep RGBA as is
            pass
        elif original_mode == 'RGB':
            # Keep RGB as is
            pass
        elif original_mode == 'P' and transparency is not None:
            # Indexed with transparency - convert to RGBA
            img = img.convert('RGBA')
        elif original_mode == 'P':
            # Indexed without transparency - convert to RGB
            img = img.convert('RGB')
        elif original_mode == 'LA':
            # Grayscale with alpha - convert to RGBA
            img = img.convert('RGBA')
        elif original_mode == 'L' or original_mode == '1':
            # Grayscale or B&W - keep as is or convert to RGB
            if original_mode == '1':
                img = img.convert('RGB')
        else:
            # Convert other modes to RGB
            img = img.convert('RGB')
        
        # Create a new image without ICC profile
        # Get image data
        if img.mode == 'RGBA':
            data = img.tobytes('raw', 'RGBA')
            new_img = Image.frombytes('RGBA', img.size, data)
        elif img.mode == 'RGB':
            data = img.tobytes('raw', 'RGB')
            new_img = Image.frombytes('RGB', img.size, data)
        else:
            new_img = img.copy()
        
        # Re-save without ICC profile or any color space info
        # Use only minimal PNG metadata
        save_kwargs = {
            'format': 'PNG',
            'optimize': False,
        }
        
        # Add transparency if needed
        if img.mode == 'RGBA' or (original_mode == 'P' and transparency is not None):
            if img.mode == 'RGBA':
                pass  # Already RGBA
        
        new_img.save(file_path, **save_kwargs)
        
        return True, has_icc
    except Exception as e:
        return False, str(e)

def main():
    icons_dir = Path(r'd:\source\repos\ShahFaisalGfG\gfgLock\src\assets\icons')
    
    if not icons_dir.exists():
        print(f"Error: Icon directory not found at {icons_dir}")
        return
    
    # Find all PNG files
    png_files = list(icons_dir.glob('*.png'))
    
    if not png_files:
        print(f"No PNG files found in {icons_dir}")
        return
    
    print(f"Found {len(png_files)} PNG file(s) to process (aggressive mode):")
    print()
    
    fixed_count = 0
    for png_file in sorted(png_files):
        print(f"Processing: {png_file.name}...", end=" ")
        success, info = fix_png_srgb_aggressive(str(png_file))
        
        if success:
            if info:
                print(f"✓ Fixed (stripped sRGB profile)")
            else:
                print(f"✓ Stripped profiles (clean PNG)")
            fixed_count += 1
        else:
            print(f"✗ Error: {info}")
    
    print()
    print(f"Successfully processed {fixed_count}/{len(png_files)} PNG files")
    print("All PNG files have been cleaned and sRGB warnings should be eliminated.")

if __name__ == '__main__':
    main()
