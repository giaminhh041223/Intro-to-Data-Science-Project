import pandas as pd
from googleapiclient.discovery import build
from langdetect import detect
import os
import re
import datetime
import calendar
import random

API_KEY = "AIzaSyBdJTPCqZtQNLhxbeDMp7NJeG73XhGWWdk" 
youtube = build('youtube', 'v3', developerKey=API_KEY)

def sanitize_filename(name):
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = name.replace('/', '-').replace('\\', '-')
    return name[:100].strip()

def get_video_id_from_url(video_url):
    pattern = r'(?:v=|\/embed\/|youtu\.be\/)([a-zA-Z0-9_-]{11})'
    match = re.search(pattern, video_url)
    if match:
        return match.group(1)
    return None

def get_channel_id_from_url(channel_url):
    print(f"Analyzing channel link: {channel_url}")
    try:
        match_id = re.search(r'\/channel\/(UC[a-zA-Z0-9_-]{22,})', channel_url)
        if match_id:
            print(f"Found Channel ID directly: {match_id.group(1)}")
            return match_id.group(1)

        match_handle = re.search(r'\/(@[a-zA-Z0-9_.-]+)', channel_url)
        if match_handle:
            handle = match_handle.group(1)
            print(f"Found Handle: {handle}. Looking up ID...")
            request = youtube.search().list(
                part="id", q=handle, type="channel", maxResults=1
            )
            response = request.execute()
            if response['items']:
                channel_id = response['items'][0]['id']['channelId']
                print(f"ID Found: {channel_id}")
                return channel_id
        
        match_user = re.search(r'\/user\/([a-zA-Z0-9_-]+)', channel_url)
        if match_user:
            username = match_user.group(1)
            print(f"Looking up ID for username: {username}...")
            request = youtube.channels().list(part="id", forUsername=username)
            response = request.execute()
            if response['items']:
                channel_id = response['items'][0]['id']
                print(f"ID Found: {channel_id}")
                return channel_id
        
        match_vanity = re.search(r'\/c\/([a-zA-Z0-9_.-]+)', channel_url)
        search_term = None
        if match_vanity:
             search_term = match_vanity.group(1)
        else:
             last_part = channel_url.rstrip('/').split('/')[-1]
             if last_part not in ['videos', 'playlists', 'about', 'featured'] and not last_part.startswith('@'):
                 search_term = last_part
        
        if search_term:
            print(f"Looking up ID using term (fallback): {search_term}...")
            request = youtube.search().list(
                part="id", q=search_term, type="channel", maxResults=1
            )
            response = request.execute()
            if response['items']:
                channel_id = response['items'][0]['id']['channelId']
                print(f"ID Found: {channel_id}")
                return channel_id

        print("Error: Could not find Channel ID from the provided link.")
        return None
    except Exception as e:
        print(f"Critical error fetching Channel ID: {e}")
        return None

def get_date_inputs():
    while True:
        start_date_str = input("  Enter START date (YYYY-MM-DD): ")
        try:
            dt_start = datetime.datetime.strptime(start_date_str, "%Y-%m-%d")
            break
        except ValueError:
            print("  Error: Invalid date format. Please use YYYY-MM-DD.")
    
    while True:
        end_date_str = input("  Enter END date (YYYY-MM-DD): ")
        try:
            dt_end = datetime.datetime.strptime(end_date_str, "%Y-%m-%d")
            if dt_end < dt_start:
                print("  Error: End date cannot be before start date.")
            else:
                break
        except ValueError:
            print("  Error: Invalid date format. Please use YYYY-MM-DD.")
    
    published_after = dt_start.isoformat("T") + "Z"
    published_before = (dt_end + datetime.timedelta(days=1)).isoformat("T") + "Z"
    
    print(f"  -> Finding videos from {published_after} to {published_before}")
    return published_after, published_before

def get_month_range_input():
    while True:
        start_month_str = input("  Enter START MONTH (YYYY-MM): ")
        try:
            dt_start = datetime.datetime.strptime(start_month_str, "%Y-%m")
            break
        except ValueError:
            print("  Error: Invalid format. Please use YYYY-MM.")
    
    while True:
        end_month_str = input("  Enter END MONTH (YYYY-MM): ")
        try:
            dt_end_month = datetime.datetime.strptime(end_month_str, "%Y-%m")
            
            if dt_end_month < dt_start:
                print("  Error: End month cannot be before start month.")
                continue

            _, last_day = calendar.monthrange(dt_end_month.year, dt_end_month.month)
            dt_end = dt_end_month.replace(day=last_day)
            
            print(f"  -> Automatically selected range from {dt_start.date()} to {dt_end.date()}")
            break
        except ValueError:
            print("  Error: Invalid format. Please use YYYY-MM.")

    published_after = dt_start.isoformat("T") + "Z"
    published_before = (dt_end + datetime.timedelta(days=1)).isoformat("T") + "Z"
    
    return published_after, published_before

def get_videos_from_channel(channel_id, published_after, published_before, verbose=True):
    video_ids = []
    next_page_token = None
    if verbose:
        print(f"Searching videos for Channel ID: {channel_id}...")
    
    while True:
        try:
            request = youtube.search().list(
                part="id",
                channelId=channel_id,
                publishedAfter=published_after,
                publishedBefore=published_before,
                type="video",
                order="date", 
                maxResults=50,
                pageToken=next_page_token
            )
            response = request.execute()
            
            for item in response['items']:
                video_ids.append(item['id']['videoId'])
                
            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break 
                
        except Exception as e:
            print(f"Error searching for videos (process might stop abruptly): {e}")
            break
            
    return video_ids

def get_random_video_per_month(channel_id):
    selected_video_ids = []
    
    while True:
        start_month_str = input("  Enter START MONTH (YYYY-MM): ")
        try:
            dt_start = datetime.datetime.strptime(start_month_str, "%Y-%m")
            break
        except ValueError:
            print("  Error: Invalid format. Please use YYYY-MM.")
    
    while True:
        end_month_str = input("  Enter END MONTH (YYYY-MM): ")
        try:
            dt_end = datetime.datetime.strptime(end_month_str, "%Y-%m")
            if dt_end < dt_start:
                print("  Error: End month cannot be before start month.")
                continue
            break
        except ValueError:
            print("  Error: Invalid format. Please use YYYY-MM.")

    current_date = dt_start
    print("\n  >>> STARTING MONTHLY SCAN FOR RANDOM VIDEOS <<<")

    while current_date <= dt_end:
        _, last_day = calendar.monthrange(current_date.year, current_date.month)
        month_start_dt = current_date
        month_end_dt = current_date.replace(day=last_day)
        
        published_after = month_start_dt.isoformat("T") + "Z"
        published_before = (month_end_dt + datetime.timedelta(days=1)).isoformat("T") + "Z"
        
        month_str = month_start_dt.strftime('%Y-%m')
        print(f"  Scanning month: {month_str} ...", end=" ")
        
        videos = get_videos_from_channel(channel_id, published_after, published_before, verbose=False)
        
        if videos:
            random_video = random.choice(videos)
            selected_video_ids.append(random_video)
            print(f"Found {len(videos)} videos. Selected random ID: {random_video}")
        else:
            print("No videos found.")
        
        if current_date.month == 12:
            current_date = current_date.replace(year=current_date.year + 1, month=1)
        else:
            current_date = current_date.replace(month=current_date.month + 1)
            
    return selected_video_ids

def get_video_details(video_id):
    try:
        request = youtube.videos().list(
            part="snippet",
            id=video_id
        )
        response = request.execute()
        
        if not response['items']:
            print(f"Error: Video not found with ID: {video_id}")
            return None, None, None

        snippet = response['items'][0]['snippet']
        video_title = snippet['title']
        channel_name = snippet['channelTitle']
        upload_date_iso = snippet['publishedAt'] 
        
        return video_title, channel_name, upload_date_iso
        
    except Exception as e:
        print(f"Error fetching video details: {e}")
        return None, None, None

def get_comments(video_id):
    comments = []
    next_page_token = None
    print("  Starting comment extraction...")
    
    while True:
        try:
            request = youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=100,
                pageToken=next_page_token,
                textFormat="plainText", 
                order="time" 
            )
            response = request.execute()
            
            for item in response['items']:
                snippet = item['snippet']['topLevelComment']['snippet']
                comments.append({
                    'Comment ID': item['id'],
                    'Author': snippet['authorDisplayName'],
                    'Content': snippet['textDisplay'],
                    'Publish Date': snippet['publishedAt'],
                    'Like Count': snippet['likeCount'],
                    'Reply Count': item['snippet']['totalReplyCount']
                })

            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break
                
        except Exception as e:
            print(f"  Error fetching comments (comments might be disabled): {e}")
            break
            
    return pd.DataFrame(comments)

def filter_english(df):
    def is_english(text):
        if pd.isna(text) or not isinstance(text, str) or len(text.strip()) < 5:
            return False
        try:
            return detect(text) == 'en'
        except:
            return False

    print("  Filtering English comments...")
    df.loc[:, 'Detected Language'] = df['Content'].apply(lambda x: detect(x) if is_english(x) else 'Other')
    df_english = df[df['Detected Language'] == 'en'].copy()
    return df_english.drop(columns=['Detected Language'])

def process_video(video_id):
    print(f"\nProcessing Video ID: {video_id}")
    print("--------------------------------------------------")
    
    video_title, channel_name, upload_date_iso = get_video_details(video_id) 

    if not video_title or not channel_name:
        print(f"Could not fetch info for video {video_id}. Skipping...")
        return 

    print(f"  > Video: {video_title}")
    print(f"  > Channel: {channel_name}")

    upload_date_str = upload_date_iso.split('T')[0] 
    month_folder_name = upload_date_str[0:7]     

    base_channel_folder = sanitize_filename(channel_name)
    clean_video_title = sanitize_filename(video_title)
    output_folder_path = os.path.join(base_channel_folder, month_folder_name)
    os.makedirs(output_folder_path, exist_ok=True)

    file_name_base = f"{upload_date_str}_{clean_video_title}"
    OUTPUT_FILE_ALL = os.path.join(output_folder_path, f"{file_name_base}_all_comments.csv")
    OUTPUT_FILE_EN = os.path.join(output_folder_path, f"{file_name_base}_english_comments.csv")

    print(f"  > Save directory: ./{output_folder_path}/")

    df_all = get_comments(video_id)

    if df_all.empty:
        print("  No comments extracted. Done.")
        return

    df_english = filter_english(df_all)
    df_all.to_csv(OUTPUT_FILE_ALL, index=False, encoding='utf-8-sig')
    print(f"  Saved {len(df_all)} (all) to: {OUTPUT_FILE_ALL}")

    if not df_english.empty:
        df_english.to_csv(OUTPUT_FILE_EN, index=False, encoding='utf-8-sig')
        print(f"  Saved {len(df_english)} (English) to: {OUTPUT_FILE_EN}")
    else:
        print("  No English comments found after filtering.")
    print("--------------------------------------------------")

def main():
    print("YOUTUBE COMMENT EXTRACTOR PROGRAM")
    print("========================================")
    print("Please select mode:")
    print("  1: Extract from a SINGLE video link.")
    print("  2: Bulk extract by CHANNEL (custom YYYY-MM-DD range).")
    print("  3: Bulk extract by CHANNEL (YYYY-MM range - ALL videos).")
    print("  4: Bulk extract by CHANNEL (YYYY-MM range - RANDOM 1 video per month).")
    
    while True:
        choice = input("Enter your choice (1, 2, 3, or 4): ")
        if choice in ['1', '2', '3', '4']:
            break
        print("Invalid choice.")
        
    if choice == '1':
        print("\n[Mode 1: Single Video]")
        video_url = input("▶ Please enter YouTube video URL: ")
        video_id = get_video_id_from_url(video_url)
        
        if video_id:
            process_video(video_id)
        else:
            print("ERROR: Invalid video link.")

    elif choice in ['2', '3', '4']:
        if choice == '2':
            print("\n[Mode 2: Bulk by Channel (Custom Date)]")
        elif choice == '3':
            print("\n[Mode 3: Bulk by Channel (Month Range - All)]")
        else:
            print("\n[Mode 4: Bulk by Channel (Month Range - Random 1/Month)]")

        channel_url = input("▶ Please enter YouTube CHANNEL URL: ")
        channel_id = get_channel_id_from_url(channel_url)
        
        if not channel_id:
            print("Could not find Channel. Exiting.")
            return

        video_ids = []

        if choice == '4':
            video_ids = get_random_video_per_month(channel_id)
        else:
            if choice == '2':
                published_after, published_before = get_date_inputs()
            else:
                published_after, published_before = get_month_range_input() 
            
            video_ids = get_videos_from_channel(
                channel_id, 
                published_after, 
                published_before
            )
        
        total_videos = len(video_ids)
        if total_videos == 0:
            print("No videos found to process.")
            return
            
        print(f"\n✅ QUEUED TOTAL {total_videos} VIDEOS. STARTING BATCH SCAN...")
        
        for i, video_id in enumerate(video_ids):
            print(f"\n===== Video {i+1} / {total_videos} =====")
            try:
                process_video(video_id)
            except Exception as e:
                print(f"!!! EXCEPTION processing video {video_id}: {e}")
                print("!!! Skipping this video and continuing...")
        
        print(f"\n✅ FINISHED: Processed {total_videos} videos.")

if __name__ == "__main__":
    main()