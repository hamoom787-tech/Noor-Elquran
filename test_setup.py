"""
Quick test script to verify the setup
"""

import os
import sys

def check_python_version():
    """Check Python version"""
    version = sys.version_info
    if version.major >= 3 and version.minor >= 8:
        print(f"✓ Python {version.major}.{version.minor}.{version.micro} - OK")
        return True
    else:
        print(f"✗ Python {version.major}.{version.minor}.{version.micro} - يجب استخدام Python 3.8 أو أحدث")
        return False

def check_dependencies():
    """Check required Python packages"""
    required_packages = [
        'flask',
        'flask_cors',
        'requests',
        'PIL',
        'arabic_reshaper',
        'bidi'
    ]
    
    all_ok = True
    for package in required_packages:
        try:
            __import__(package)
            print(f"✓ {package} - مثبت")
        except ImportError:
            print(f"✗ {package} - غير مثبت")
            all_ok = False
    
    return all_ok

def check_ffmpeg():
    """Check if FFmpeg is available"""
    import subprocess
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
        if result.returncode == 0:
            print("✓ FFmpeg - متوفر")
            return True
        else:
            print("✗ FFmpeg - غير متوفر")
            return False
    except Exception as e:
        print(f"✗ FFmpeg - غير متوفر ({str(e)})")
        return False

def check_directories():
    """Check required directories"""
    dirs = ['vision', 'audio', 'outputs', 'data']
    all_ok = True
    
    for dir_name in dirs:
        if os.path.exists(dir_name):
            print(f"✓ مجلد {dir_name}/ - موجود")
        else:
            print(f"✗ مجلد {dir_name}/ - غير موجود")
            all_ok = False
    
    return all_ok

def check_background_videos():
    """Check for background videos"""
    vision_dir = 'vision'
    if os.path.exists(vision_dir):
        mp4_files = [f for f in os.listdir(vision_dir) if f.endswith('.mp4')]
        if mp4_files:
            print(f"✓ فيديوهات الخلفية - موجود ({len(mp4_files)} ملف)")
            return True
        else:
            print("⚠ فيديوهات الخلفية - لا توجد ملفات .mp4 في مجلد vision/")
            print("  يرجى إضافة ملفات فيديو للخلفية")
            return False
    return False

def main():
    print("=" * 60)
    print("🔍 فحص إعداد مولد فيديوهات القرآن الكريم")
    print("=" * 60)
    print()
    
    print("📋 فحص المتطلبات:")
    print("-" * 60)
    
    checks = {
        'Python': check_python_version(),
        'المكتبات': check_dependencies(),
        'FFmpeg': check_ffmpeg(),
        'المجلدات': check_directories(),
        'فيديوهات الخلفية': check_background_videos()
    }
    
    print()
    print("=" * 60)
    print("📊 ملخص النتائج:")
    print("=" * 60)
    
    passed = sum(1 for v in checks.values() if v)
    total = len(checks)
    
    for name, status in checks.items():
        status_icon = "✓" if status else "✗"
        print(f"{status_icon} {name}")
    
    print()
    print(f"النتيجة: {passed}/{total} فحوصات نجحت")
    print()
    
    if all(checks.values()):
        print("🎉 ممتاز! كل شيء جاهز!")
        print("يمكنك الآن تشغيل التطبيق باستخدام: python main.py")
    else:
        print("⚠ يرجى إصلاح المشاكل أعلاه قبل التشغيل")
        print()
        
        if not checks['المكتبات']:
            print("💡 لتثبيت المكتبات: pip install -r requirements.txt")
        
        if not checks['FFmpeg']:
            print("💡 لتثبيت FFmpeg: قم بتحميله من https://ffmpeg.org/download.html")
        
        if not checks['فيديوهات الخلفية']:
            print("💡 ضع ملفات فيديو .mp4 في مجلد vision/")
    
    print()

if __name__ == '__main__':
    main()
