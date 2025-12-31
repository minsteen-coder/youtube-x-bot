import feedparser
import tweepy
import google.generativeai as genai
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
import os
import datetime

# --- Configuration ---
RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id=UCnwTpaRmErJXgJTrVixeSNA"
LAST_VIDEO_FILE = "last_video_id.txt"

# API Keys (Environment Variables)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TWITTER_API_KEY = os.environ.get("TWITTER_API_KEY")
TWITTER_API_SECRET = os.environ.get("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.environ.get("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_TOKEN_SECRET = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET")

def get_latest_video():
    """Fetches the latest video from the RSS feed."""
    feed = feedparser.parse(RSS_URL)
    if feed.entries:
        return feed.entries[0]
    return None

def get_last_processed_video_id():
    """Reads the last processed video ID from a file."""
    if os.path.exists(LAST_VIDEO_FILE):
        with open(LAST_VIDEO_FILE, "r") as f:
            return f.read().strip()
    return None

def save_last_processed_video_id(video_id):
    """Saves the processed video ID to a file."""
    with open(LAST_VIDEO_FILE, "w") as f:
        f.write(video_id)

def get_video_transcript(video_id):
    """Fetches the transcript of the video."""
    try:
        # Check if get_transcript exists (older versions or static method availability)
        if hasattr(YouTubeTranscriptApi, 'get_transcript'):
             transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko'])
        else:
             # Fallback for versions where get_transcript is not a static method on the class directly
             # Based on inspection, use instance method or available static helper if any, 
             # but the safest way per the error is to use the instance approach if static fails,
             # However, typically YouTubeTranscriptApi is a static class in many examples. 
             # Let's try the standard static way first, but since it failed, we use the instance way found in help.
             # Actually, the help says `fetch` is an instance method.
             ytt_api = YouTubeTranscriptApi()
             transcript = ytt_api.fetch(video_id, languages=['ko'])

        formatter = TextFormatter()
        return formatter.format_transcript(transcript)
    except Exception as e:
        print(f"Error fetching transcript: {e}")
        return None

def summarize_with_gemini(text, video_title):
    """Summarizes the text using Google Gemini."""
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set.")
    
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')

    prompt = f"""
    당신은 인기 있는 소셜 미디어 인플루언서입니다. 
    아래는 유튜브 영상 "{video_title}"의 자막(또는 내용)입니다.
    이 내용을 바탕으로 X(구 트위터)에 올릴 매력적이고 핵심적인 요약글을 작성해주세요.
    
    조건:
    1. 한국어로 작성하세요.
    2. 핵심 내용을 3~5줄 내외로 요약하세요.
    3. 문체는 친근하고 매력적으로 ("해요"체 등).
    4. 해시태그를 2~3개 포함하세요.
    5. 전체 길이는 250자를 넘지 않도록 주의하세요 (링크 제외).
    
    내용:
    {text[:10000]}  # Limit input text length to avoid token limits if necessary
    """
    
    response = model.generate_content(prompt)
    return response.text

def post_to_twitter(text, video_link):
    """Posts the summary and link to X (Twitter)."""
    if not all([TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET]):
        raise ValueError("Twitter API keys are missing.")

    client = tweepy.Client(
        consumer_key=TWITTER_API_KEY,
        consumer_secret=TWITTER_API_SECRET,
        access_token=TWITTER_ACCESS_TOKEN,
        access_token_secret=TWITTER_ACCESS_TOKEN_SECRET
    )

    tweet_content = f"{text}\n\n{video_link}"
    
    try:
        response = client.create_tweet(text=tweet_content)
        print(f"Tweet posted successfully! ID: {response.data['id']}")
        return True
    except Exception as e:
        print(f"Error posting to Twitter: {e}")
        return False

def main():
    print(f"Checking for new videos at {datetime.datetime.now()}...")
    
    latest_video = get_latest_video()
    if not latest_video:
        print("No videos found in feed.")
        return

    video_id = latest_video.yt_videoid
    video_title = latest_video.title
    video_link = latest_video.link

    last_id = get_last_processed_video_id()

    print(f"Latest video: {video_title} ({video_id})")
    print(f"Last processed video: {last_id}")

    if video_id == last_id:
        print("No new video found. Exiting.")
        return

    print("New video detected! Processing...")

    # 1. Get Transcript
    transcript = get_video_transcript(video_id)
    content_to_summarize = transcript
    
    if not transcript:
        print("Transcript not available. Using description instead.")
        # If no transcript, use title and description (from feed)
        content_to_summarize = f"제목: {video_title}\n\n설명: {latest_video.summary}"

    # 2. Summarize
    try:
        summary = summarize_with_gemini(content_to_summarize, video_title)
        print("Summary generated:")
        print(summary)
    except Exception as e:
        print(f"Failed to generate summary: {e}")
        return

    # 3. Post to Twitter
    if post_to_twitter(summary, video_link):
        save_last_processed_video_id(video_id)
        print(f"Successfully processed video: {video_id}")
    else:
        print("Failed to post to Twitter.")

if __name__ == "__main__":
    main()
