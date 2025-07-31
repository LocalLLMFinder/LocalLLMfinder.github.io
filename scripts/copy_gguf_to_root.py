"""
Simple script to copy the generated gguf_models.json from scripts/data to website output directory.
This ensures index.html can access the updated file.
"""

import shutil
from pathlib import Path
import os
import sys

# Add the scripts directory to the path so we can import the config
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def copy_gguf_to_website():
    """Copy gguf_models.json from scripts/data to website output directory."""
    
    try:
        # Load configuration to get the correct output directory
        from config_system import load_configuration
        config = load_configuration()
        
        # Define paths using configuration
        script_dir = Path(__file__).parent
        data_file = script_dir / config.storage.data_directory / "gguf_models.json"
        website_output_dir = Path(config.storage.website_output_directory)
        website_file = website_output_dir / "gguf_models.json"
        
    except Exception as e:
        print(f"⚠️ Could not load configuration, using default paths: {e}")
        # Fallback to default paths
        script_dir = Path(__file__).parent
        data_file = script_dir / "data" / "gguf_models.json"
        root_dir = script_dir.parent
        website_file = root_dir / "gguf_models.json"
        website_output_dir = root_dir
    
    print(f"📁 Script directory: {script_dir}")
    print(f"📁 Website output directory: {website_output_dir}")
    print(f"📄 Source file: {data_file}")
    print(f"📄 Target file: {website_file}")
    
    # Check if source file exists
    if not data_file.exists():
        print(f"❌ Source file not found: {data_file}")
        print("   Make sure you've run the workflow first:")
        print("   python update_models.py --retention-mode retention")
        return False
    
    try:
        # Get file sizes for comparison
        source_size = data_file.stat().st_size
        target_size = website_file.stat().st_size if website_file.exists() else 0
        
        print(f"📊 Source file size: {source_size:,} bytes")
        print(f"📊 Target file size: {target_size:,} bytes")
        
        # Load and transform the data to legacy format
        import json
        
        with open(data_file, 'r', encoding='utf-8') as f:
            retention_models = json.load(f)
        
        # Transform to legacy format expected by website
        legacy_models = []
        for model in retention_models:
            model_id = model.get('id', '')
            
            # Extract family and name from model ID
            if '/' in model_id:
                parts = model_id.split('/')
                family = parts[0]
                name = '/'.join(parts[1:]) if len(parts) > 1 else parts[0]
            else:
                family = 'Unknown'
                name = model_id
            
            # Extract architecture from tags or model name
            architecture = 'Unknown'
            tags = model.get('tags', [])
            for tag in tags:
                if any(arch in tag.lower() for arch in ['llama', 'mistral', 'gemma', 'qwen', 'phi', 'deepseek']):
                    architecture = tag.split(':')[-1] if ':' in tag else tag
                    break
            
            # If no architecture found in tags, try to extract from model name
            if architecture == 'Unknown':
                model_name_lower = model_id.lower()
                if 'llama' in model_name_lower:
                    architecture = 'Llama'
                elif 'mistral' in model_name_lower:
                    architecture = 'Mistral'
                elif 'gemma' in model_name_lower:
                    architecture = 'Gemma'
                elif 'qwen' in model_name_lower:
                    architecture = 'Qwen'
                elif 'phi' in model_name_lower:
                    architecture = 'Phi'
                elif 'deepseek' in model_name_lower:
                    architecture = 'DeepSeek'
            
            legacy_model = {
                'modelId': model_id,
                'files': [{'filename': f.get('filename', f.get('name', ''))} 
                         for f in model.get('files', [])],
                'downloads': model.get('downloads', 0),
                'lastModified': model.get('lastModified') or model.get('created_at'),
                'family': family,
                'name': name,
                'architecture': architecture,
                # Add freshness fields
                'lastSynced': model.get('lastSynced'),
                'freshnessStatus': model.get('freshnessStatus', 'unknown'),
                'hoursSinceModified': model.get('hoursSinceModified'),
                'hoursSinceSynced': model.get('hoursSinceSynced', 0.0)
            }
            legacy_models.append(legacy_model)
        
        # Ensure website output directory exists
        website_output_dir.mkdir(parents=True, exist_ok=True)
        
        # Write the transformed data
        with open(website_file, 'w', encoding='utf-8') as f:
            json.dump(legacy_models, f, indent=2, ensure_ascii=False)
        
        # Verify the transformation
        new_target_size = website_file.stat().st_size
        print(f"✅ File transformed and saved successfully!")
        print(f"📊 Transformed {len(legacy_models)} models to legacy format")
        print(f"📊 New target file size: {new_target_size:,} bytes")
        
        if new_target_size == source_size:
            print("✅ File sizes match - copy successful!")
        else:
            print("⚠️ File sizes don't match - there may be an issue")
        
        return True
        
    except Exception as e:
        print(f"❌ Error copying file: {e}")
        return False

if __name__ == "__main__":
    print("🔄 Copying gguf_models.json from data directory to website output directory...")
    success = copy_gguf_to_website()
    
    if success:
        print("\n🎉 Success! Your index.html should now load the updated data.")
        print("💡 You can now test your website with the new model data.")
    else:
        print("\n❌ Copy failed. Please check the error messages above.")