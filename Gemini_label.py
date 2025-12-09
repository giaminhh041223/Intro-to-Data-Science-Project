import google.generativeai as genai
from google.api_core import exceptions
import pandas as pd
from tqdm import tqdm
import time
import os
import glob
import re

# ==========================================
# CONFIGURATION
# ==========================================
# Get key at: https://aistudio.google.com/app/apikey
GEMINI_API_KEY = "none" 

# Model Configuration
genai.configure(api_key=GEMINI_API_KEY)

# --- SMART MODEL SELECTION ---
def initialize_model():
    print("Checking available AI models...")
    try:
        supported_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        # Priority 1: Flash 8b (Often has higher limits)
        for m in supported_models:
            if 'flash-8b' in m:
                print(f"✅ Found High-Speed Model: {m}")
                return genai.GenerativeModel(m)

        # Priority 2: Standard Flash
        for m in supported_models:
            if 'flash' in m and '1.5' in m:
                print(f"✅ Found Standard Flash Model: {m}")
                return genai.GenerativeModel(m)
        
        # Priority 3: Any Flash
        for m in supported_models:
            if 'flash' in m:
                print(f"✅ Found Flash Model: {m}")
                return genai.GenerativeModel(m)

        print(f"⚠️ No 'Flash' model found. Using first available: {supported_models[0]}")
        print("⚠️ NOTE: This model might be slow (2 requests/min).")
        return genai.GenerativeModel(supported_models[0])
        
    except Exception as e:
        print(f"⚠️ Error listing models: {e}")
        print("⚠️ Forcing 'gemini-1.5-flash'...")
        return genai.GenerativeModel('gemini-1.5-flash')

model = initialize_model()

# ==========================================
# 1. DEFINE PROMPT (SCORING RULES)
# ==========================================
def get_system_prompt(video_title, channel_name, comment_text):
    """
    Create prompt to send to AI based on your rules.
    """
    prompt = f"""
    You are an expert data analyst evaluating the quality and value of YouTube comments.
    
    Your task is to assign a "Value Score" (Integer 0-5) to the comment based on how much it contributes to the video's community or discussion. Use these strict criteria:

    0 (Spam/Garbage): Completely unrelated, unintelligible, self-promotion, scams, or random character strings.
    1 (Low Effort/Noise): Single words ("First", "Nice"), generic emojis only, or generic praise/hate that could apply to any video (e.g., "Love you", "Hate this").
    2 (Surface Level): Simple, specific reactions to visual/audio elements ("Music is loud", "Nice car"), or stating simple preferences without elaboration.
    3 (Conversational): Comments that share a relevant personal story, ask a specific question about the content, or point out specific timestamps/moments.
    4 (Constructive/Critical): Detailed feedback on the video's production/content, logical arguments for/against the video's points, or substantial discussion of the topic.
    5 (High Value/Insightful): Expert knowledge sharing, correcting facts with evidence, deep analysis of the video's themes, or comments that are highly informative and act as supplementary content.

    ---
    CONTEXT:
    Channel: {channel_name}
    Video Title: {video_title}
    Comment: {comment_text}
    ---
    
    YOUR RATING (0-5):
    """
    return prompt

# ==========================================
# 2. API CALL FUNCTION WITH RETRY LOGIC
# ==========================================
def get_label_from_ai(video_title, channel_name, comment_text):
    prompt = get_system_prompt(video_title, channel_name, comment_text)
    
    max_retries = 5
    base_wait = 10
    
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            result = response.text.strip()
            
            if result.isdigit():
                return int(result)
            else:
                match = re.search(r'\d', result)
                return int(match.group()) if match else None

        except exceptions.ResourceExhausted as e:
            # Handle 429 Rate Limit Errors
            wait_time = base_wait * (2 ** attempt) # Exponential backoff: 10s, 20s, 40s...
            
            # Try to extract exact wait time from error message
            error_str = str(e)
            retry_match = re.search(r'retry in (\d+(\.\d+)?)s', error_str)
            if retry_match:
                wait_time = float(retry_match.group(1)) + 1 # Add 1 second buffer
            
            print(f"\n⏳ Rate limit hit. Waiting {wait_time:.1f}s before retry {attempt+1}/{max_retries}...")
            time.sleep(wait_time)
            
        except Exception as e:
            print(f"\n❌ Error: {e}")
            return None 

    print("\n❌ Failed after max retries.")
    return None

# ==========================================
# 3. UTILITY: EXTRACT INFO FROM FILENAME
# ==========================================
def extract_info_from_filename(filepath):
    """
    Attempts to extract Video Title from filename formatted as:
    YYYY-MM-DD_VideoTitle_suffix.csv
    """
    filename = os.path.basename(filepath)
    title = filename
    
    # 1. Try to remove Date prefix (YYYY-MM-DD_)
    if len(filename) > 11 and filename[4] == '-' and filename[7] == '-':
        title = filename[11:] 

    # 2. Try to remove known suffixes
    if "_english_comments.csv" in title:
        title = title.replace("_english_comments.csv", "")
    elif "_all_comments.csv" in title:
        title = title.replace("_all_comments.csv", "")
    else:
        title = title.replace(".csv", "")
    
    return title

# ==========================================
# 4. CSV FILE PROCESSING FUNCTION
# ==========================================
def process_single_file(input_csv_path, channel_name=None, video_title=None):
    print(f"\nProcessing file: {os.path.basename(input_csv_path)}")
    df = pd.read_csv(input_csv_path)

    if not channel_name:
        channel_name = input("Enter Channel Name: ")
    
    if not video_title:
        video_title = extract_info_from_filename(input_csv_path)
        print(f"   > Inferred Title: {video_title}")

    if 'Label' not in df.columns:
        df['Label'] = -1 

    unlabeled_count = len(df[(df['Label'] == -1) | (df['Label'].isna())])
    if unlabeled_count == 0:
        print("   > All rows already labeled. Skipping.")
        return

    print(f"   > Starting auto-labeling for {unlabeled_count} comments...")
    
    for index, row in tqdm(df.iterrows(), total=df.shape[0], desc="Labeling"):
        if row['Label'] != -1 and pd.notna(row['Label']):
            continue
            
        comment = str(row['Content'])
        
        score = get_label_from_ai(video_title, channel_name, comment)
        
        if score is not None:
            df.at[index, 'Label'] = score
        
        # SAFE SPEED: 4 seconds sleep = 15 requests/minute (Free Tier Limit)
        time.sleep(4.0) 
        
        if index % 10 == 0: # Save more frequently
            df.to_csv(input_csv_path, index=False, encoding='utf-8-sig')

    df.to_csv(input_csv_path, index=False, encoding='utf-8-sig')
    
    labeled_df = df[(df['Label'] != -1) & (df['Label'].notna())]
    if not labeled_df.empty:
        mean_score = labeled_df['Label'].mean()
        print(f"   > ✅ Done. Average Quality Score: {mean_score:.2f} / 5.0")
    else:
        print("   > ⚠️ Done, but no labels generated.")

# ==========================================
# MAIN
# ==========================================
def main():
    print("=== AUTO LABELER TOOL ===")
    path_input = input("Drag and drop FOLDER or FILE here (or paste path): ").strip('"')
    
    if os.path.isfile(path_input):
        process_single_file(path_input)
        
    elif os.path.isdir(path_input):
        print(f"\n📂 Folder detected: {path_input}")
        
        default_channel = os.path.basename(os.path.normpath(path_input)) 
        channel_name = input(f"Enter Channel Name (Press Enter to use '{default_channel}'): ")
        if not channel_name.strip():
            channel_name = default_channel
            
        csv_files = glob.glob(os.path.join(path_input, "**", "*.csv"), recursive=True)
        
        if not csv_files:
            print("No CSV files found!")
            return

        print(f"Found {len(csv_files)} CSV files. Starting batch process...")
        
        for i, filepath in enumerate(csv_files):
            print(f"\n--- [{i+1}/{len(csv_files)}] ---")
            try:
                process_single_file(filepath, channel_name=channel_name)
            except Exception as e:
                print(f"Error processing {os.path.basename(filepath)}: {e}")
                
        print("\n🎉 BATCH PROCESSING COMPLETE!")
        
    else:
        print("Invalid path!")

if __name__ == "__main__":
    main()
