def parse_media(url, media_type):
    if not url or not media_type:
        return None

    url = url.strip()

    # 🔴 YouTube
    if media_type == "youtube":
        import re
        match = re.search(r"(?:v=|youtu\.be/)([^&?/]+)", url)
        if match:
            video_id = match.group(1)
            return f'''
            <iframe width="100%" height="400"
                src="https://www.youtube.com/embed/{video_id}"
                frameborder="0"
                allowfullscreen>
            </iframe>
            '''

    # 🟢 Image
    elif media_type == "image":
        if "drive.google.com" in url:

            file_id = re.search(r"/d/([\w-]+)", url).group(1)

            return f'''
            <iframe 
                src="https://drive.google.com/file/d/{file_id}/preview"
                width="100%" 
                height="400">
            </iframe>
            '''

        return f'<img src="{url}" style="width:100%; border-radius:10px;" />'

    # 🔵 Video
    elif media_type == "video":
        if "drive.google.com" in url:
            import re
            file_id = re.search(r"/d/([\w-]+)", url).group(1)
            url = f"https://drive.google.com/file/d/{file_id}/preview"

            return f'''
            <iframe src="{url}" width="100%" height="400"></iframe>
            '''

        return f'''
        <video width="100%" controls>
            <source src="{url}">
        </video>
        '''

    return None