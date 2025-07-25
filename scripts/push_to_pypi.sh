#!/bin/bash

# Script to push all mindtrace packages to PyPI
# Usage: ./scripts/push_to_pypi.sh [testpypi|pypi]
# 
# Defaults to testpypi if no repository specified
# Requires ~/.pypirc configuration with standard sections:
# [testpypi]  # For Test PyPI
# [pypi]      # For production PyPI

# Default to testpypi if no repository specified
REPOSITORY=${1:-testpypi}

# Validate repository argument
if [[ "$REPOSITORY" != "testpypi" && "$REPOSITORY" != "pypi" ]]; then
    print_error "Invalid repository. Use 'testpypi' or 'pypi'"
    echo "Usage: $0 [testpypi|pypi]"
    exit 1
fi

# Don't exit on error - we want to continue with other packages

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_status "Pushing packages to $REPOSITORY..."

# List of all packages 
PACKAGES=(
    ""  # Empty string for the main mindtrace package
    "core"
    "services"
    "registry"
    "database"
    "storage"
    "apps"
    "cluster"
    "datalake"
    "hardware"
    "jobs"
    "models"
    "automation"
    "ui"
)

# Counter for successful uploads
SUCCESS_COUNT=0
FAILED_PACKAGES=()

# Function to upload a single package
upload_package() {
    local package=$1
    
    # Handle the main mindtrace package (empty string) vs sub-packages
    if [[ -z "$package" ]]; then
        local package_name="mindtrace"
        local package_pattern="dist/mindtrace-0.1.0*"
        local repository_name="$REPOSITORY"
        print_status "Uploading $package_name..."
    else
        local package_name="mindtrace-$package"
        local package_pattern="dist/mindtrace_${package}-0.1.0*"
        local repository_name="$REPOSITORY"
        print_status "Uploading $package_name..."
    fi
    
    # Check if dist directory exists in root
    if [[ ! -d "dist" ]]; then
        print_error "No dist directory found in root. Run 'uv build --all-packages' first."
        return 1
    fi
    
    # Find the package files in root dist directory
    local package_files=$(ls $package_pattern 2>/dev/null || true)
    
    if [[ -z "$package_files" ]]; then
        print_error "No package files found for $package_name in dist/"
        return 1
    fi
    
    # Upload with skip-existing flag from root directory using package-specific repository
    # Capture the output and exit code
    local upload_output
    local upload_exit_code
    
    upload_output=$(uv run twine upload --repository "$repository_name" --skip-existing $package_pattern 2>&1)
    upload_exit_code=$?
    
    # Check if upload was successful or if files were skipped
    if [[ $upload_exit_code -eq 0 ]] || echo "$upload_output" | grep -q "Skipping.*because it appears to already exist"; then
        print_success "$package_name uploaded successfully (or already exists)"
        ((SUCCESS_COUNT++))
    else
        print_error "Failed to upload $package_name"
        echo "$upload_output"
        FAILED_PACKAGES+=("$package_name")
    fi
}

# Main execution
print_status "Starting upload process for ${#PACKAGES[@]} packages (including main mindtrace package)..."

for package in "${PACKAGES[@]}"; do
    upload_package "$package"
done

# Summary
echo
print_status "Upload Summary:"
print_success "Successfully uploaded: $SUCCESS_COUNT packages"

if [[ ${#FAILED_PACKAGES[@]} -gt 0 ]]; then
    print_error "Failed packages:"
    for package in "${FAILED_PACKAGES[@]}"; do
        echo "  - $package"
    done
    exit 1
else
    print_success "All packages uploaded successfully!"
fi 
