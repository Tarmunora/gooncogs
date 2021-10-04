import asyncio
import urllib
from collections import OrderedDict
import struct
import discord
from redbot.core import commands, Config, checks
import discord.errors
from redbot.core.bot import Red
from typing import *
from fastapi import Request, Depends, HTTPException
from fastapi.responses import JSONResponse
import re
import time
import functools
import inspect
import collections

class SpacebeeCommands(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot

    def format_whois(self, response):
        count = int(response['count'])
        out = []
        for i in range(1, count + 1):
            rolestuff = response.get(f"role{i}", "jobless")
            if response.get(f"dead{i}"):
                rolestuff += " DEAD"
            if response.get(f"t{i}"):
                rolestuff += " \N{REGIONAL INDICATOR SYMBOL LETTER T}"
            line = response.get(f"name{i}", "-") + \
                " (" + response.get(f"ckey{i}", "-") + ") " + rolestuff
            out.append(line)
        if out:
            return '\n'.join(out)
        return "No one found."

    def ckeyify(self, text):
        return ''.join(c.lower() for c in text if c.isalnum())

    @commands.command()
    @checks.admin()
    async def locate(self, ctx: commands.Context, *, who: str):
        """Locates a ckey on all servers."""
        who = self.ckeyify(who)
        goonservers = self.bot.get_cog('GoonServers')
        servers = [s for s in goonservers.servers if s.type == 'goon']
        futures = [asyncio.Task(goonservers.send_to_server(s, "status", to_dict=True)) for s in servers]
        message = None
        done, pending = [], futures
        old_text = None
        while pending:
            when = asyncio.FIRST_COMPLETED if message else asyncio.ALL_COMPLETED
            done, pending = await asyncio.wait(pending, timeout=0.2, return_when=when)
            if not done:
                continue
            lines = []
            for server, f in zip(servers, futures):
                if f.done() and f.exception() is None:
                    result = f.result()
                    server_found = []
                    for k, v in result.items():
                        if k.startswith('player') and who in self.ckeyify(v):
                            server_found.append(v)
                    if not server_found:
                        continue
                    if len(server_found) == 1:
                        lines.append(f"{server.full_name}: **{server_found[0]}**")
                    else:
                        lines.append(f"{server.full_name}:")
                        lines.extend(f"\t**{p}**" for p in server_found)
            if not lines:
                continue
            text = "\n".join(lines)
            if len(text) > 2000:
                text = text[:1900] + "\n[Message too long, shorten your query]"
            if message is None:
                message = await ctx.send(text)
            elif text != old_text:
                await message.edit(content=text)
            old_text = text
        if not message:
            await ctx.send("No one found.")

    @commands.command()
    @checks.admin()
    async def whois(self, ctx: commands.Context, server_id: str, *, query: str):
        """Looks for a person on a given Goonstation server."""
        goonservers = self.bot.get_cog('GoonServers')
        response = await goonservers.send_to_server_safe(server_id, {
                'type': "whois",
                'target': query,
            }, ctx, to_dict=True)
        if response is None:
            return
        await ctx.send(self.format_whois(response))

    @commands.command()
    async def players(self, ctx: commands.Context, server_id: str):
        """Lists players on a given Goonstation server."""
        goonservers = self.bot.get_cog('GoonServers')
        response = await goonservers.send_to_server_safe(server_id, "status", ctx.message, to_dict=True)
        if response is None:
            return
        players = []
        try:
            for i in range(int(response['players'])):
                players.append(response[f'player{i}'])
        except KeyError:
            await ctx.message.reply("That server is not responding correctly.")
            return
        players.sort()
        if players:
            await ctx.message.reply(", ".join(players))
        else:
            await ctx.message.reply("No players.")

    @commands.command()
    @checks.admin()
    async def ooc(self, ctx: commands.Context, server_id: str, *, message: str):
        """Sends an OOC message to a given Goonstation server."""
        goonservers = self.bot.get_cog('GoonServers')
        await goonservers.send_to_server_safe(server_id, {
                'type': "ooc",
                'msg': message,
                'nick': f"(Discord) {ctx.author.name}",
            }, ctx.message, react_success=True)

    @commands.command()
    @checks.admin()
    async def antags(self, ctx: commands.Context, server_id: str):
        """Lists antagonists on a given Goonstation server."""
        goonservers = self.bot.get_cog('GoonServers')
        response = await goonservers.send_to_server_safe(server_id, {
                'type': "antags",
            }, ctx, to_dict=True)
        if response is None:
            return
        await ctx.send(self.format_whois(response))

    @commands.command()
    @checks.admin()
    async def ailaws(self, ctx: commands.Context, server_id: str):
        """Lists current AI laws on a given Goonstation server."""
        goonservers = self.bot.get_cog('GoonServers')
        response = await goonservers.send_to_server_safe(server_id, {
                'type': "ailaws",
            }, ctx, to_dict=True)
        if response is None:
            return
        if response == 0.0:
            await ctx.send("Round hasn't started yet.")
            return
        out = []
        for key, value in sorted(response.items()):
            try:
                key = int(key)
            except ValueError:
                continue
            out.append(f"{key}: {value}")
        if out:
            await ctx.send('\n'.join(out))
        else:
            await ctx.send("No AI laws.")

    @commands.command(aliases=["hcheck"])
    @checks.admin()
    async def scheck(self, ctx: commands.Context, server_id: str):
        """Checks server health of a given Goonstation server."""
        goonservers = self.bot.get_cog('GoonServers')
        response = await goonservers.send_to_server_safe(server_id, {
                'type': "health",
            }, ctx, to_dict=True)
        if response is None:
            return
        await ctx.send(f"CPU: {response['cpu']}\ntime scaling: {response['time']}")

    @commands.command()
    @checks.admin()
    async def rev(self, ctx: commands.Context, server_id: str):
        """Checks code revision of a given Goonstation server."""
        goonservers = self.bot.get_cog('GoonServers')
        response = await goonservers.send_to_server_safe(server_id, {
                'type': "rev",
            }, ctx, to_dict=True)
        if response is None:
            return
        rev, author = response['msg'].split(" by ")
        await ctx.send(response['msg'] + "\nhttps://github.com/goonstation/goonstation/commit/" + rev)

    @commands.command()
    @checks.admin()
    async def version(self, ctx: commands.Context, server_id: str):
        """Checks BYOND version of a given Goonstation server."""
        goonservers = self.bot.get_cog('GoonServers')
        response = await goonservers.send_to_server_safe(server_id, {
                'type': "version",
            }, ctx, to_dict=True)
        if response is None:
            return
        await ctx.send(f"BYOND {response['major']}.{response['minor']}\nGoonhub: {response['goonhub_api']}")

    @commands.command()
    @checks.admin()
    async def delay(self, ctx: commands.Context, server_id: str):
        """Delays a Goonstation round end."""
        goonservers = self.bot.get_cog('GoonServers')
        response = await goonservers.send_to_server_safe(server_id, {
                'type': "delay",
                'nick': ctx.message.author.name,
            }, ctx, to_dict=True)
        if response is None:
            return
        await ctx.send(response['msg'])

    @commands.command()
    @checks.admin()
    async def undelay(self, ctx: commands.Context, server_id: str):
        """Undelays a Goonstation round end."""
        goonservers = self.bot.get_cog('GoonServers')
        response = await goonservers.send_to_server_safe(server_id, {
                'type': "undelay",
                'nick': ctx.message.author.name,
            }, ctx, to_dict=True)
        if response is None:
            return
        await ctx.send(response['msg'])

    @commands.command()
    @checks.is_owner()
    async def rickroll(self, ctx: commands.Context, server_id: str):
        """Test command to check if playing music works."""
        goonservers = self.bot.get_cog('GoonServers')
        response = await goonservers.send_to_server_safe(server_id, {
                'type': "youtube",
                'data': '{"key":"Pali6","title":"test","duration":4,"file":"https://qoret.com/dl/uploads/2019/07/Rick_Astley_-_Never_Gonna_Give_You_Up_Qoret.com.mp3"}',
            }, ctx, to_dict=True)
        if response is None:
            return
        await ctx.message.add_reaction("\N{FROG FACE}")

    @commands.command()
    @checks.admin()
    async def admins(self, ctx: commands.Context, server_id: str):
        """Lists admins in a given Goonstation server."""
        goonservers = self.bot.get_cog('GoonServers')
        response = await goonservers.send_to_server_safe(server_id, "admins", ctx.message, to_dict=True)
        if response is None:
            return
        admins = []
        try:
            for i in range(int(response['admins'])):
                admin = response[f'admin{i}']
                if admin.startswith('~'):
                    continue
                admins.append(admin)
        except KeyError:
            await ctx.message.reply("That server is not responding correctly.")
            return
        admins.sort()
        if admins:
            await ctx.message.reply(", ".join(admins))
        else:
            await ctx.message.reply("No admins.")

    @commands.command()
    @checks.admin()
    async def mentors(self, ctx: commands.Context, server_id: str):
        """Lists mentors in a given Goonstation server."""
        goonservers = self.bot.get_cog('GoonServers')
        response = await goonservers.send_to_server_safe(server_id, "mentors", ctx.message, to_dict=True)
        if response is None:
            return
        mentors = []
        try:
            for i in range(int(response['mentors'])):
                mentor = response[f'mentor{i}']
                mentors.append(mentor)
        except KeyError:
            await ctx.message.reply("That server is not responding correctly.")
            return
        mentors.sort()
        if mentors:
            await ctx.message.reply(", ".join(mentors))
        else:
            await ctx.message.reply("No mentors.")
