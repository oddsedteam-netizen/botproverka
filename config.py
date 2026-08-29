import os

# Токен бота — сначала из переменной окружения, потом из значения по умолчанию
BOT_TOKEN = os.getenv("BOT_TOKEN", "8432991209:AAHz57v4Yc4pSrr0NeK24cK5hMWA70rhiWE")

# ID администратора
ADMIN_ID = int(os.getenv("ADMIN_ID", "1269379743"))

# Ссылка на ТГК
TGK_LINK = os.getenv("TGK_LINK", "https://t.me/Checking_the_angel")