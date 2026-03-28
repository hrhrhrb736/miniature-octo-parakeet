"""
Run this ONCE on your PC to generate SESSION_STRING.
Then paste the output into Railway environment variables.

Install first:  pip install telethon
"""

import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

async def main():
    API_ID   = input("Enter API_ID: ").strip()
    API_HASH = input("Enter API_HASH: ").strip()

    async with TelegramClient(StringSession(), int(API_ID), API_HASH) as client:
        print("\n✅ Your SESSION_STRING is:\n")
        print(client.session.save())
        print("\nCopy the above string and add it as SESSION_STRING in Railway.")

if __name__ == "__main__":
    asyncio.run(main())
