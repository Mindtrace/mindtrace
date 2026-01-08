# Stereo Camera Setup

## Installation of Basler Stereo ace Supplementary Package

The Stereo ace Supplementary Package provides the GenTL Producer needed to use Basler Stereo ace camera systems with pypylon.

### Platform Support

- ✅ **Linux**: Full support (Debian and tar.gz methods)
- ❌ **Windows**: Not supported (Basler does not provide Windows version)

### Prerequisites

1. **Basler pylon SDK** must be installed first
   - Install using `mindtrace-camera-basler-install` or manually from [Basler website](https://www.baslerweb.com/en/downloads/software-downloads/)

2. **pypylon** Python package
   ```bash
   pip install mindtrace-hardware[stereo-basler]
   ```

### Installation Methods

#### Method 1: Console Command (Recommended)

**Simplest method** - Uses installed console script:

```bash
# Install (automatically downloads from GitHub)
mindtrace-stereo-basler-install

# Install to custom directory
mindtrace-stereo-basler-install --install-dir ~/my_stereo_cameras

# Uninstall
mindtrace-stereo-basler-uninstall
```

#### Method 2: Direct Script Execution

**For development** - Run setup script directly with uv:

```bash
# Default installation (tarball to ~/.local/share/pylon_stereo)
uv run python mindtrace/hardware/stereo_cameras/setup/setup_stereo_ace.py

# OR with custom directory
uv run python mindtrace/hardware/stereo_cameras/setup/setup_stereo_ace.py \
    --install-dir ~/my_stereo_cameras
```

No manual download needed! The script will:
1. Download the package from GitHub releases
2. Extract and install to specified directory
3. Generate environment setup script automatically

#### Method 3: Debian Package (System-wide - Requires sudo)

**Advantages:**
- System-wide installation to /opt/pylon
- Automatic environment configuration after logout/login
- Cleaner system integration

**Steps:**

1. Install using console command or direct script:
   ```bash
   # Console command (automatic download)
   mindtrace-stereo-basler-install --method deb

   # OR with direct script
   uv run python mindtrace/hardware/stereo_cameras/setup/setup_stereo_ace.py \
       --method deb

   # OR with local package
   mindtrace-stereo-basler-install --method deb \
       --package /path/to/pylon-supplementary-package-for-stereo-ace-1.0.3_amd64.deb
   ```

2. Setup environment (automatic after logout/login, or run immediately):
   ```bash
   source /opt/pylon/bin/pylon-setup-env.sh /opt/pylon
   ```

3. Make persistent (add to ~/.bashrc):
   ```bash
   echo 'source /opt/pylon/bin/pylon-setup-env.sh /opt/pylon' >> ~/.bashrc
   ```

#### Method 4: Manual Package Installation (Advanced)

If you already downloaded the package manually:

```bash
# With local package file
mindtrace-stereo-basler-install --method tarball \
    --package /path/to/pylon-supplementary-package-for-stereo-ace-1.0.3_x86_64_setup.tar.gz \
    --install-dir ~/my_stereo_cameras

# Setup environment
source ~/my_stereo_cameras/setup_stereo_env.sh

# Make persistent (add to ~/.bashrc)
echo 'source ~/my_stereo_cameras/setup_stereo_env.sh' >> ~/.bashrc
```

### Verification

After installation and environment setup, verify:

```bash
# Check environment variable
echo $GENICAM_GENTL64_PATH
# Should contain: /path/to/pylon/lib/gentlproducer/gtl

# Test with Python
python -c "from pypylon import pylon; print('GenTL Producers:', [tl.GetFullName() for tl in pylon.TlFactory.GetInstance().EnumerateTls()])"
# Should show: GenTL/basler_xw
```

### Uninstallation

#### Using Console Commands (Recommended):
```bash
# Debian package
mindtrace-stereo-basler-uninstall --method deb

# tar.gz archive (default location)
mindtrace-stereo-basler-uninstall

# tar.gz archive (custom location)
mindtrace-stereo-basler-uninstall --install-dir ~/my_stereo_cameras
```

#### Using Direct Script:
```bash
# Debian package
uv run python mindtrace/hardware/stereo_cameras/setup/setup_stereo_ace.py \
    --method deb --uninstall

# tar.gz archive
uv run python mindtrace/hardware/stereo_cameras/setup/setup_stereo_ace.py \
    --method tarball --install-dir ~/.local/share/pylon_stereo --uninstall
```

**Don't forget to remove the environment setup line from ~/.bashrc!**

### Manual Installation (Alternative)

If you prefer manual installation:

#### Debian Package:
```bash
sudo apt-get install ./pylon-supplementary-package-for-stereo-ace-1.0.3_amd64.deb
source /opt/pylon/bin/pylon-setup-env.sh /opt/pylon
```

#### tar.gz Archive:
```bash
# Extract outer archive
tar xf pylon-supplementary-package-for-stereo-ace-1.0.3_x86_64_setup.tar.gz
cd pylon-supplementary-package-for-stereo-ace-1.0.3_x86_64_setup

# Extract to destination
tar -C ~/my_install_dir -xzf pylon-supplementary-package-for-stereo-ace-1.0.3_x86_64.tar.gz

# Setup environment
export PYLON_ROOT=~/my_install_dir/pylon
export GENICAM_GENTL64_PATH=$PYLON_ROOT/lib/gentlproducer/gtl
export LD_LIBRARY_PATH=$PYLON_ROOT/lib:$PYLON_ROOT/lib/gentlproducer/gtl:$LD_LIBRARY_PATH
```

### Troubleshooting

**GenTL Producer not found:**
- Verify GENICAM_GENTL64_PATH is set correctly
- Check that basler_xw.cti exists: `ls $GENICAM_GENTL64_PATH/basler_xw.cti`
- Source the environment script in every new terminal or add to ~/.bashrc

**No cameras found:**
- Ensure cameras are powered and connected
- Verify I/O cables connect both cameras to pattern projector
- Check network connectivity (ping camera IPs)
- Run StereoViewer to test hardware: `$PYLON_ROOT/bin/StereoViewer`

**Permission denied:**
- For Debian package: use sudo
- For tar.gz: ensure installation directory is writable

### Integration with MindTrace

After successful installation, the Stereo ace backend will automatically detect the GenTL Producer and be available for use:

```python
from mindtrace.hardware.stereo_cameras.backends.basler import BaslerStereoBackend

# Backend will use the installed GenTL Producer
camera = BaslerStereoBackend("40644640")  # Serial number
await camera.initialize()
```

### Resources

- Basler Stereo ace Documentation: Installed at `$PYLON_ROOT/share/pylon/doc/stereo-ace/`
- Python Samples: `$PYLON_ROOT/share/pylon/Samples/Stereo_ace/Python/`
- StereoViewer: `$PYLON_ROOT/bin/StereoViewer`
- Official Download: https://www.baslerweb.com/en/downloads/software-downloads/
