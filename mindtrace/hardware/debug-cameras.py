#!/usr/bin/env python3
"""
Debug script to test camera detection on different platforms
"""
import os
import platform
import subprocess
import sys

def detect_platform():
    """Detect if we're running on Windows or Linux"""
    system = platform.system().lower()
    print(f"Platform: {system}")
    print(f"Platform details: {platform.platform()}")
    
    # Check if we're in Docker
    if os.path.exists('/.dockerenv'):
        print("Running inside Docker container")
    else:
        print("Running on host system")
    
    return system

def test_opencv_cameras():
    """Test OpenCV camera detection"""
    print("\n=== Testing OpenCV Camera Detection ===")
    try:
        import cv2
        print(f"OpenCV version: {cv2.__version__}")
        
        # Test camera indices 0-5
        for i in range(6):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                ret, frame = cap.read()
                if ret:
                    print(f"✅ Camera {i}: Working - {frame.shape}")
                else:
                    print(f"⚠️  Camera {i}: Opens but can't capture")
                cap.release()
            else:
                print(f"❌ Camera {i}: Not available")
                
    except ImportError:
        print("❌ OpenCV not available")
    except Exception as e:
        print(f"❌ OpenCV error: {e}")

def test_basler_cameras():
    """Test Basler camera detection"""
    print("\n=== Testing Basler Camera Detection ===")
    try:
        from pypylon import pylon
        print("✅ pypylon available")
        
        # Get transport layer factory
        tlFactory = pylon.TlFactory.GetInstance()
        
        # Test general device enumeration
        devices = tlFactory.EnumerateDevices()
        print(f"Found {len(devices)} Basler devices:")
        
        for i, device in enumerate(devices):
            try:
                print(f"  Device {i}:")
                print(f"    Name: {device.GetFriendlyName()}")
                print(f"    Model: {device.GetModelName()}")
                print(f"    Serial: {device.GetSerialNumber()}")
                print(f"    Interface: {device.GetDeviceClass()}")
                if hasattr(device, 'GetIpAddress'):
                    print(f"    IP: {device.GetIpAddress()}")
            except Exception as e:
                print(f"    Error reading device info: {e}")
                
        # Test GigE specifically
        try:
            gige_tl = tlFactory.CreateTl("BaslerGigE")
            if gige_tl:
                gige_devices = gige_tl.EnumerateDevices()
                print(f"GigE devices: {len(gige_devices)}")
        except Exception as e:
            print(f"GigE enumeration error: {e}")
            
    except ImportError:
        print("❌ pypylon not available")
    except Exception as e:
        print(f"❌ Basler error: {e}")

def test_network_connectivity():
    """Test network connectivity for GigE cameras"""
    print("\n=== Testing Network Connectivity ===")
    
    # Show network interfaces
    try:
        if platform.system().lower() == 'windows':
            result = subprocess.run(['ipconfig'], capture_output=True, text=True)
        else:
            result = subprocess.run(['ip', 'addr', 'show'], capture_output=True, text=True)
        print("Network interfaces:")
        print(result.stdout)
    except Exception as e:
        print(f"❌ Network interface check failed: {e}")
    
    # Test ping to camera networks
    camera_networks = ['192.168.100.1', '192.168.200.1']
    for ip in camera_networks:
        try:
            if platform.system().lower() == 'windows':
                result = subprocess.run(['ping', '-n', '1', ip], 
                                      capture_output=True, text=True, timeout=5)
            else:
                result = subprocess.run(['ping', '-c', '1', ip], 
                                      capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                print(f"✅ Can reach {ip}")
            else:
                print(f"❌ Cannot reach {ip}")
        except Exception as e:
            print(f"❌ Ping to {ip} failed: {e}")

def test_usb_devices():
    """Test USB device visibility"""
    print("\n=== Testing USB Devices ===")
    try:
        # On Linux, check lsusb
        if platform.system().lower() == 'linux':
            result = subprocess.run(['lsusb'], capture_output=True, text=True)
            print("USB devices:")
            print(result.stdout)
            
            # Check video devices
            result = subprocess.run(['ls', '-la', '/dev/video*'], 
                                  capture_output=True, text=True)
            print("Video devices:")
            print(result.stdout)
        else:
            print("USB device enumeration not available on Windows in container")
    except Exception as e:
        print(f"❌ USB device check failed: {e}")

def main():
    print("🔍 Camera Detection Debug Tool")
    print("=" * 50)
    
    detect_platform()
    test_network_connectivity()
    test_usb_devices()
    test_opencv_cameras()
    test_basler_cameras()
    
    print("\n" + "=" * 50)
    print("Debug complete!")

if __name__ == "__main__":
    main()