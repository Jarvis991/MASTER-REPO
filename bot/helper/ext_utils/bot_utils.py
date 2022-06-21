from re import match as re_match, findall as re_findall
from threading import Thread, Event
from time import time
from math import ceil
from html import escape
from psutil import virtual_memory, cpu_percent, disk_usage
from requests import head as rhead
from urllib.request import urlopen
from telegram import InlineKeyboardMarkup

from bot.helper.telegram_helper.bot_commands import BotCommands
from bot import download_dict, download_dict_lock, STATUS_LIMIT, botStartTime, DOWNLOAD_DIR
from bot.helper.telegram_helper.button_build import ButtonMaker

MAGNET_REGEX = r"magnet:\?xt=urn:btih:[a-zA-Z0-9]*"

URL_REGEX = r"(?:(?:https?|ftp):\/\/)?[\w/\-?=%.]+\.[\w/\-?=%.]+"

COUNT = 0
PAGE_NO = 1


class MirrorStatus:
    STATUS_UPLOADING = "Uploading...📤"
    STATUS_DOWNLOADING = "Downloading...📥"
    STATUS_CLONING = "Cloning...♻️"
    STATUS_WAITING = "Queued...💤"
    STATUS_FAILED = "Failed 🚫. Cleaning Download..."
    STATUS_PAUSE = "Paused...⛔️"
    STATUS_ARCHIVING = "Archiving...🔐"
    STATUS_EXTRACTING = "Extracting...📂"
    STATUS_SPLITTING = "Splitting...✂️"
    STATUS_CHECKING = "CheckingUp...📝"
    STATUS_SEEDING = "Seeding...🌧"

SIZE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']


class setInterval:
    def __init__(self, interval, action):
        self.interval = interval
        self.action = action
        self.stopEvent = Event()
        thread = Thread(target=self.__setInterval)
        thread.start()

    def __setInterval(self):
        nextTime = time() + self.interval
        while not self.stopEvent.wait(nextTime - time()):
            nextTime += self.interval
            self.action()

    def cancel(self):
        self.stopEvent.set()

def get_readable_file_size(size_in_bytes) -> str:
    if size_in_bytes is None:
        return '0B'
    index = 0
    while size_in_bytes >= 1024:
        size_in_bytes /= 1024
        index += 1
    try:
        return f'{round(size_in_bytes, 2)}{SIZE_UNITS[index]}'
    except IndexError:
        return 'File too large'

def getDownloadByGid(gid):
    with download_dict_lock:
        for dl in list(download_dict.values()):
            status = dl.status()
            if (
                status
                not in [
                    MirrorStatus.STATUS_ARCHIVING,
                    MirrorStatus.STATUS_EXTRACTING,
                    MirrorStatus.STATUS_SPLITTING,
                ]
                and dl.gid() == gid
            ):
                return dl
    return None

def getAllDownload(req_status: str):
    with download_dict_lock:
        for dl in list(download_dict.values()):
            status = dl.status()
            if status not in [MirrorStatus.STATUS_ARCHIVING, MirrorStatus.STATUS_EXTRACTING, MirrorStatus.STATUS_SPLITTING] and dl:
                if req_status == 'down' and (status not in [MirrorStatus.STATUS_SEEDING,
                                                            MirrorStatus.STATUS_UPLOADING,
                                                            MirrorStatus.STATUS_CLONING]):
                    return dl
                elif req_status == 'up' and status == MirrorStatus.STATUS_UPLOADING:
                    return dl
                elif req_status == 'clone' and status == MirrorStatus.STATUS_CLONING:
                    return dl
                elif req_status == 'seed' and status == MirrorStatus.STATUS_SEEDING:
                    return dl
                elif req_status == 'all':
                    return dl
    return None

def get_progress_bar_string(status):
    completed = status.processed_bytes() / 8
    total = status.size_raw() / 8
    p = 0 if total == 0 else round(completed * 100 / total)
    p = min(max(p, 0), 100)
    cFull = p // 8
    p_str = '▰' * cFull
    p_str += '▱' * (12 - cFull)
    p_str = f"[{p_str}]"
    return p_str

def get_readable_message():
    with download_dict_lock:
        msg = ""
        if STATUS_LIMIT is not None:
            tasks = len(download_dict)
            global pages
            pages = ceil(tasks/STATUS_LIMIT)
            if PAGE_NO > pages and pages != 0:
                globals()['COUNT'] -= STATUS_LIMIT
                globals()['PAGE_NO'] -= 1
        for index, download in enumerate(list(download_dict.values())[COUNT:], start=1):
            msg += f"<b>📄 File Name :</b> <code>{escape(str(download.name()))}</code>"
            msg += f"\n<b>🗃️ Total Size : {download.size()}</b>"
            msg += f"\n<b>🌀 Status : {download.status()}</b>"
            if download.status() not in [
                MirrorStatus.STATUS_ARCHIVING,
                MirrorStatus.STATUS_EXTRACTING,
                MirrorStatus.STATUS_SPLITTING,
                MirrorStatus.STATUS_SEEDING,
            ]:
                msg += f"\n🚀 <b>{get_progress_bar_string(download)} {download.progress()}</b> 💨"
                if download.status() == MirrorStatus.STATUS_CLONING:
                    msg += f"\n♻️ <b>Cloned : {get_readable_file_size(download.processed_bytes())} of {download.size()}</b>"
                elif download.status() == MirrorStatus.STATUS_UPLOADING:
                    msg += f"\n🔺 <b>Uploaded : {get_readable_file_size(download.processed_bytes())} of {download.size()}</b>"
                else:
                    msg += f"\n🔻 <b>Downloaded : {get_readable_file_size(download.processed_bytes())} of {download.size()}</b>"
                msg += f"\n<b>⚡️ Speed : {download.speed()}</b>" \
                           f"\n<b>⏳ ETA : {download.eta()}</b>"
                try:
                    msg += f"\n<b>🔍 Tracker :- 🧲 Seeds : {download.aria_download().num_seeders}</b>" \
                            f" | <b>🧲 Peers : {download.aria_download().connections}</b>"
                except:
                    pass
                try:
                    msg += f"\n<b>🔍 Tracker :- 🧲 Seeds : {download.torrent_info().num_seeds}</b>" \
                            f" | <b>🧲 Leechs : {download.torrent_info().num_leechs}</b>"
                except:
                    pass
                if download.message.chat.type != 'private':
                    try:
                        chatid = str(download.message.chat.id)[4:]
                        msg += f'\n<b>Source Msg: </b><a href="https://t.me/c/{chatid}/{download.message.message_id}">Click Here</a>'
                    except:
                        pass
                msg += f'\n<b>User:</b> ️<code>{download.message.from_user.first_name}</code>️(<code>{download.message.from_user.id}</code>)'  
                    except:
                        pass
                msg += f'\n<b>User:</b> ️<code>{download.message.from_user.first_name}</code>️(<code>{download.message.from_user.id}</code>)'           
                msg += f"\n<b>🔰 GID : {download.gid()}</b>" \
                       f"\n<b>🚫 Cancel :</b> <code>/{BotCommands.CancelMirror} {download.gid()}</code>"
            elif download.status() == MirrorStatus.STATUS_SEEDING:
                msg += f"\n<b>🗃️ Size : {download.size()}</b>"
                msg += f"\n<b>⚡️ Speed : {get_readable_file_size(download.torrent_info().upspeed)}/s</b>"
                msg += f" | <b>🔺 Uploaded: {get_readable_file_size(download.torrent_info().uploaded)}</b>"
                msg += f"\n<b>🌧 Ratio : {round(download.torrent_info().ratio, 3)}</b>"
                msg += f" | <b>⏰ Time : {get_readable_time(download.torrent_info().seeding_time)}</b>"
                msg += f"\n<b>🚫 Cancel :</b> <code>/{BotCommands.CancelMirror} {download.gid()}</code>"
            else:
                msg += f"\n<b>🗃️ Size : {download.size()}</b>"
            msg += "\n\n"
            if STATUS_LIMIT is not None and index == STATUS_LIMIT:
                break
        bmsg = f"<b>📊 Performance Meter 📊</b>\n\n<b>🖥 CPU            : {cpu_percent()}%</b>\n<b>🗃 DISK           : {get_readable_file_size(disk_usage(DOWNLOAD_DIR).free)}</b>"
        bmsg += f"\n<b>⚙️ RAM           : {virtual_memory().percent}%</b>\n<b>⏰ UPTIME     : {get_readable_time(time() - botStartTime)}</b>"
        dlspeed_bytes = 0
        upspeed_bytes = 0
        for download in list(download_dict.values()):
            spd = download.speed()
            if download.status() == MirrorStatus.STATUS_DOWNLOADING:
                if 'K' in spd:
                    dlspeed_bytes += float(spd.split('K')[0]) * 1024
                elif 'M' in spd:
                    dlspeed_bytes += float(spd.split('M')[0]) * 1048576
            elif download.status() == MirrorStatus.STATUS_UPLOADING:
                if 'KB/s' in spd:
                    upspeed_bytes += float(spd.split('K')[0]) * 1024
                elif 'MB/s' in spd:
                    upspeed_bytes += float(spd.split('M')[0]) * 1048576
        bmsg += f"\n\n<b>⚡️ Internet Speed Meter ⚡️</b>\n\n<b>🔻 D : {get_readable_file_size(dlspeed_bytes)}/s</b> | <b>🔺 U : {get_readable_file_size(upspeed_bytes)}/s</b>"
        if STATUS_LIMIT is not None and tasks > STATUS_LIMIT:
            msg += f"<b>📌 Page : {PAGE_NO}/{pages}</b> | <b>🔖 Tasks : {tasks}</b>\n\n"
            buttons = ButtonMaker()
            buttons.sbutton("↩️ Previous ↩️", "status pre")
            buttons.sbutton("↪️ Next ↪️", "status nex")
            button = InlineKeyboardMarkup(buttons.build_menu(2))
            return msg + bmsg, button
        return msg + bmsg, ""

def turn(data):
    try:
        with download_dict_lock:
            global COUNT, PAGE_NO
            if data[1] == "nex":
                if PAGE_NO == pages:
                    COUNT = 0
                    PAGE_NO = 1
                else:
                    COUNT += STATUS_LIMIT
                    PAGE_NO += 1
            elif data[1] == "pre":
                if PAGE_NO == 1:
                    COUNT = STATUS_LIMIT * (pages - 1)
                    PAGE_NO = pages
                else:
                    COUNT -= STATUS_LIMIT
                    PAGE_NO -= 1
        return True
    except:
        return False

def get_readable_time(seconds: int) -> str:
    result = ''
    (days, remainder) = divmod(seconds, 86400)
    days = int(days)
    if days != 0:
        result += f'{days} Days '
    (hours, remainder) = divmod(remainder, 3600)
    hours = int(hours)
    if hours != 0:
        result += f'{hours} Hours '
    (minutes, seconds) = divmod(remainder, 60)
    minutes = int(minutes)
    if minutes != 0:
        result += f'{minutes} Minutes '
    seconds = int(seconds)
    result += f'{seconds} Seconds '
    return result

def is_url(url: str):
    url = re_findall(URL_REGEX, url)
    return bool(url)

def is_gdrive_link(url: str):
    return "drive.google.com" in url

def is_gdtot_link(url: str):
    url = re_match(r'https?://.+\.gdtot\.\S+', url)
    return bool(url)

def is_mega_link(url: str):
    return "mega.nz" in url or "mega.co.nz" in url

def get_mega_link_type(url: str):
    if "folder" in url:
        return "folder"
    elif "file" in url:
        return "file"
    elif "/#F!" in url:
        return "folder"
    return "file"

def is_magnet(url: str):
    magnet = re_findall(MAGNET_REGEX, url)
    return bool(magnet)

def new_thread(fn):
    """To use as decorator to make a function call threaded.
    Needs import
    from threading import Thread"""

    def wrapper(*args, **kwargs):
        thread = Thread(target=fn, args=args, kwargs=kwargs)
        thread.start()
        return thread

    return wrapper

def get_content_type(link: str) -> str:
    try:
        res = rhead(link, allow_redirects=True, timeout=5, headers = {'user-agent': 'Wget/1.12'})
        content_type = res.headers.get('content-type')
    except:
        try:
            res = urlopen(link, timeout=5)
            info = res.info()
            content_type = info.get_content_type()
        except:
            content_type = None
    return content_type

