import discord
from discord.utils import get
from discord import FFmpegPCMAudio
import youtube_dl
import asyncio
from async_timeout import timeout
from functools import partial
from discord.ext import commands
import itertools

bot = commands.Bot(command_prefix='@mention',help_command=None)

@bot.event
async def on_ready(): 
    print(f"Logged in as {bot.user}")

# intents = discord.Intents.default()
# intents.members = True
# client = discord.Client(intents = intents)

# @bot.event
# async def on_member_join(member):
#     guild = bot.get_guild(863331917704200192)
#     channel = guild.get_channel(863331917704200194)
#     emBed = discord.Embed(title = "Welcome",color = 0xf4e274, description = f"Online {member.mention} ")
#     emBed.set_thumbnail(url = "https://www.img.in.th/images/e243ecaf243badf260112c6b904d523b.th.jpg")
#     await channel.send(embed= emBed)

# @bot.event
# async def on_member_remove(member):
#     guild = bot.get_guild(863331917704200192)
#     channel = guild.get_channel(863331917704200194)
#     emBed = discord.Embed(title = "Good bye",color = 0xf4e274, description = f"{member.name}")
#     emBed.set_thumbnail(url = "https://www.img.in.th/images/bbe483a70a8ffcc153dc1221dbd142cf.th.jpg")
#     await bot.send_message(embed= emBed)

@bot.command() 
async def help(ctx): 
    emBed = discord.Embed(title="Nattasak Commands", description="All commands", color=0xFE6F5E)
    emBed.add_field(name="@mention help", value="Commands", inline="False")
    emBed.add_field(name="@mention music", value="song commands", inline="False")
    emBed.add_field(name="@mention leave", value="leave the room", inline="False")
    emBed.set_thumbnail(url='https://www.img.in.th/images/f73877a36eb531f6bbc65b1fa381984e.th.jpg')
    emBed.set_footer(text="Nattasak-Bot", icon_url='https://www.img.in.th/images/3ab51c65d5193ae1d017bc01ac582f77.th.jpg')
    await ctx.channel.send(embed=emBed)

@bot.command() 
async def music(ctx): 
    emBed = discord.Embed(title="คNattasak Commands", description="All commands", color=0xc48bd0)
    emBed.add_field(name="@mention p", value="play songs", inline="False")
    emBed.add_field(name="@mention stop", value="stop song", inline="False")
    emBed.add_field(name="@mention pause", value="pause song", inline="False")
    emBed.add_field(name="@mention resume", value="resume song", inline="False")
    emBed.add_field(name="@mention skip", value="skip song", inline="False")
    emBed.add_field(name="@mention queue", value="song queue", inline="False")
    emBed.set_thumbnail(url='https://www.img.in.th/images/08f5e28f225bd96b286d05348ae3bce3.th.jpg')
    emBed.set_footer(text="Nattasak-Bot", icon_url='https://www.img.in.th/images/df9ccdb9f54e90732005730b9f92b5cf.th.jpg')
    await ctx.channel.send(embed=emBed)

##############################################################

youtube_dl.utils.bug_reports_message = lambda: ''

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0' # bind to ipv4 since ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
    'options': '-vn',
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5" ## song will end if no this line
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):

    def __init__(self, source, *, data, requester):
        super().__init__(source)
        self.requester = requester

        self.title = data.get('title')
        self.web_url = data.get('webpage_url')

        # YTDL info dicts (data) have other useful information you might want
        # https://github.com/rg3/youtube-dl/blob/master/README.md

    def __getitem__(self, item: str):
        """Allows us to access attributes similar to a dict.
        This is only useful when you are NOT downloading.
        """
        return self.__getattribute__(item)

    @classmethod
    async def create_source(cls, ctx, search: str, *, loop, download=False):
        loop = loop or asyncio.get_event_loop()

        to_run = partial(ytdl.extract_info, url=search, download=download)
        data = await loop.run_in_executor(None, to_run)

        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]

        await ctx.send(f'```ini@mention n[✅ add music {data["title"]} in queue]@mention n```') #delete after can be added

        if download:
            source = ytdl.prepare_filename(data)
        else:
            return {'webpage_url': data['webpage_url'], 'requester': ctx.author, 'title': data['title']}

        return cls(discord.FFmpegPCMAudio(source, **ffmpeg_options), data=data, requester=ctx.author)

    @classmethod
    async def regather_stream(cls, data, *, loop):
        """Used for preparing a stream, instead of downloading.
        Since Youtube Streaming links expire."""
        loop = loop or asyncio.get_event_loop()
        requester = data['requester']

        to_run = partial(ytdl.extract_info, url=data['webpage_url'], download=False)
        data = await loop.run_in_executor(None, to_run)

        return cls(discord.FFmpegPCMAudio(data['url'], **ffmpeg_options), data=data, requester=requester)

class MusicPlayer:
    """A class which is assigned to each guild using the bot for Music.
    This class implements a queue and loop, which allows for different guilds to listen to different playlists
    simultaneously.
    When the bot disconnects from the Voice it's instance will be destroyed.
    """

    __slots__ = ('bot', '_guild', '_channel', '_cog', 'queue', 'next', 'current', 'np', 'volume')

    def __init__(self, ctx):
        self.bot = ctx.bot
        self._guild = ctx.guild
        self._channel = ctx.channel
        self._cog = ctx.cog

        self.queue = asyncio.Queue()
        self.next = asyncio.Event()

        self.np = None  # Now playing message
        self.volume = .5
        self.current = None

        ctx.bot.loop.create_task(self.player_loop())

    async def player_loop(self):
        """Our main player loop."""
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            self.next.clear()

            try:
                # Wait for the next song. If we timeout cancel the player and disconnect...
                async with timeout(300):  # 5 minutes...
                    source = await self.queue.get()
            except asyncio.TimeoutError:
                del players[self._guild]
                return await self.destroy(self._guild)

            if not isinstance(source, YTDLSource):
                # Source was probably a stream (not downloaded)
                # So we should regather to prevent stream expiration
                try:
                    source = await YTDLSource.regather_stream(source, loop=self.bot.loop)
                except Exception as e:
                    await self._channel.send(f'🚫 There was an error processing the song.@mention n'
                                             f'```css\n[{e}]\n```')
                    continue

            source.volume = self.volume
            self.current = source

            self._guild.voice_client.play(source, after=lambda _: self.bot.loop.call_soon_threadsafe(self.next.set))
            self.np = await self._channel.send(f'**🔊 playing songs : ** `{source.title}`  '
                                               f'`{source.requester}`')
            await self.next.wait()

            # Make sure the FFmpeg process is cleaned up.
            source.cleanup()
            self.current = None

            try:
                # We are no longer playing this song...
                await self.np.delete()
            except discord.HTTPException:
                pass

    async def destroy(self, guild):
        """Disconnect and cleanup the player."""
        del players[self._guild]
        await self._guild.voice_client.disconnect()
        return self.bot.loop.create_task(self._cog.cleanup(guild))

#######################################################################

@bot.command() 
async def p(ctx,* , search: str ) : 
    channel = ctx.author.voice.channel
    voice_client = get(bot.voice_clients,guild = ctx.guild)

    if voice_client == None:
        await ctx.channel.send("🎶 play songs")
        await channel.connect()
        voice_client = get(bot.voice_clients,guild = ctx.guild)
    await ctx.trigger_typing()

    _player = get_player(ctx)
    source = await YTDLSource.create_source(ctx, search, loop = bot.loop, download = False)
    await _player.queue.put(source)

players = {}
def get_player(ctx):
    try:
        player = players[ctx.guild.id]
    except:
        player = MusicPlayer(ctx)
        players[ctx.guild.id] = player
    return player

@bot.command() 
async def stop(ctx):
    voice_client = get(bot.voice_clients,guild = ctx.guild)
    if voice_client == None:
        await ctx.channel.send("stop song")
        return
    if voice_client.channel @mention = ctx.author.voice.channel:
        await ctx.channel.send("📢 Bot on the voice {0}".format(voice_client.channel) + " cannot stop song")
        return
    voice_client.stop()

@bot.command() 
async def pause(ctx):
    voice_client = get(bot.voice_clients,guild = ctx.guild)
    if voice_client == None:
        await ctx.channel.send("pause songs")
        return
    if voice_client.channel @mention = ctx.author.voice.channel:
        await ctx.channel.send("📢 Bot on the voice {0}".format(voice_client.channel) + " cannot stop song")
        return
    voice_client.pause()

@bot.command() 
async def resume(ctx):
    voice_client = get(bot.voice_clients,guild = ctx.guild)
    if voice_client == None:
        await ctx.channel.send("add songs")
        return
    if voice_client.channel @mention = ctx.author.voice.channel:
        await ctx.channel.send("📢 Bot on the voice {0}".format(voice_client.channel) + " cannot stop song")
        return
    voice_client.resume()

@bot.command()
async def queue(ctx):
    voice_client = get(bot.voice_clients, guild = ctx.guild)
    if voice_client == None or not voice_client.is_connected():
        await ctx.channel.send("queue", delete_after = 10)
        return
    player = get_player(ctx)
    if player.queue.empty():
        return await ctx.send('❌ have not songs in queue')
    
    upcoming = list(itertools.islice(player.queue._queue,0,player.queue.qsize()))
    fmt = '!n'.join(f'**`{_["title"]}`**' for _ in upcoming)
    embed = discord.Embed(title = queue {len(upcoming)} songs', description = fmt)
    await ctx.send(embed = embed)

@bot.command() 
async def skip(ctx):
    voice_client = get(bot.voice_clients, guild = ctx.guild)
    if voice_client == None or not voice_client.is_connected():
        await ctx.channel.send("skip song", delete_after = 10)
        return
    if voice_client.is_paused():
        pass
    elif not voice_client.is_playing():
        return
    voice_client.stop()
    await ctx.send(f'**`{ctx.author}`** : skip song')

@bot.command() 
async def leave(ctx):
    del players[ctx.guild.id]
    await ctx.voice_client.disconnect()


bot.run('#')
