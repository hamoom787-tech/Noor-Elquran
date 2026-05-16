from PIL import Image
import os

def convert_png_to_ico(png_path, ico_path):
    if os.path.exists(png_path):
        img = Image.open(png_path)
        # Standard icon sizes
        icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        img.save(ico_path, sizes=icon_sizes)
        print(f"Successfully created icon: {ico_path}")
    else:
        print(f"PNG not found: {png_path}")

if __name__ == "__main__":
    # Update this to the actual path of the generated icon
    png_file = "C:/Users/MEMO2007/.gemini/antigravity/brain/89ce18b4-b609-4fa3-897e-23dba88330f4/quran_reels_icon_1769556666375.png"
    convert_png_to_ico(png_file, "app_icon.ico")
