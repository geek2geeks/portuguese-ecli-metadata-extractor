from pathlib import Path
import json

def test_json_files():
    """Test JSON files accessibility and structure."""
    json_path = Path("d:/jsons")  # Your actual path - update if different
    
    print(f"Checking JSON files in: {json_path.absolute()}")
    print("-" * 50)
    
    if not json_path.exists():
        print(f"❌ Directory does not exist: {json_path}")
        print("\nPlease update the path in this script to match your actual JSON directory.")
        return
    
    # Find all JSON files recursively
    json_files = list(json_path.glob("**/*.json"))
    print(f"Found {len(json_files)} JSON files")
    
    if len(json_files) == 0:
        print("❌ No JSON files found - check your path")
        print(f"\nLooked in: {json_path.absolute()}")
        print("\nMake sure:")
        print("1. The path is correct")
        print("2. JSON files exist in the directory")
        print("3. Files have .json extension")
        return
    
    print("✅ JSON files found")
    print(f"First few files:")
    for i, file_path in enumerate(json_files[:5]):
        print(f"  {i+1}. {file_path.name}")
    
    if len(json_files) > 5:
        print(f"  ... and {len(json_files) - 5} more files")
    
    # Test loading the first JSON file
    print("\nTesting JSON structure...")
    try:
        with open(json_files[0], 'r', encoding='utf-8') as f:
            sample_data = json.load(f)
        
        print("✅ JSON files are valid and readable")
        print(f"Sample file keys: {list(sample_data.keys())[:10]}")
        
        # Check for required fields
        required_fields = ['ecli', 'extraction_method', 'extraction_timestamp']
        missing_fields = [field for field in required_fields if field not in sample_data]
        
        if missing_fields:
            print(f"⚠️  Missing required fields in sample: {missing_fields}")
        else:
            print("✅ Required fields present in sample")
            
    except json.JSONDecodeError as e:
        print(f"❌ JSON parsing error in {json_files[0].name}: {e}")
    except Exception as e:
        print(f"❌ Error reading JSON file: {e}")
    
    print(f"\n📊 Summary:")
    print(f"  - Directory: {json_path}")
    print(f"  - Total JSON files: {len(json_files):,}")
    print(f"  - Ready for processing: {'✅ Yes' if len(json_files) > 0 else '❌ No'}")

if __name__ == "__main__":
    test_json_files()