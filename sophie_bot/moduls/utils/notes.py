# Copyright (C) 2019 The Raphielscape Company LLC.
# Copyright (C) 2018-2019 MrYacha
# Copyright (C) 2017-2019 Aiogram
#
# This file is part of SophieBot.
#
# SophieBot is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# Licensed under the Raphielscape Public License, Version 1.c (the "License");
# you may not use this file except in compliance with the License.

import html
import re
import sys

from aiogram.types.inline_keyboard import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import markdown
from telethon.tl.custom import Button

from .tmarkdown_converter import tbold, titalic, tpre, tcode, tlink
from .user_details import get_user_link

from .message import get_args


BUTTONS = {}

ALLOWED_COLUMNS = [
    'parse_mode',
    'file',
    'text',
    'preview'
]


def tparse_ent(ent, text, as_html=True):
    if not text:
        return text

    etype = ent.type
    offset = ent.offset
    length = ent.length

    if sys.maxunicode == 0xffff:
        return text[offset:offset + length]

    if not isinstance(text, bytes):
        entity_text = text.encode('utf-16-le')
    else:
        entity_text = text

    entity_text = entity_text[offset * 2:(offset + length) * 2].decode('utf-16-le')

    if etype == 'bold':
        method = markdown.hbold if as_html else tbold
        return method(entity_text)
    if etype == 'italic':
        method = markdown.hitalic if as_html else titalic
        return method(entity_text)
    if etype == 'pre':
        method = markdown.hpre if as_html else tpre
        return method(entity_text)
    if etype == 'code':
        method = markdown.hcode if as_html else tcode
        return method(entity_text)
    if etype == 'url':
        return entity_text
    if etype == 'text_link':
        method = markdown.hlink if as_html else tlink
        return method(entity_text, ent.url)
    if etype == 'text_mention' and ent.user:
        return ent.user.get_mention(entity_text, as_html=as_html)

    return entity_text


def get_parsed_msg(message):
    if not message.text:
        return '', 'md'

    text = message.text or message.caption

    mode = get_msg_parse(text)
    if mode == 'html':
        as_html = True
    else:
        as_html = False

    entities = message.entities or message.caption_entities

    if not entities:
        return text, mode

    if not sys.maxunicode == 0xffff:
        text = text.encode('utf-16-le')

    result = ''
    offset = 0

    for entity in sorted(entities, key=lambda item: item.offset):
        entity_text = tparse_ent(entity, text, as_html=as_html)

        if sys.maxunicode == 0xffff:
            part = text[offset:entity.offset]
            result += part + entity_text
        else:
            part = text[offset * 2:entity.offset * 2].decode('utf-16-le')
            result += part + entity_text

        offset = entity.offset + entity.length

    if sys.maxunicode == 0xffff:
        result += text[offset:]
    else:
        result += text[offset * 2:].decode('utf-16-le')

    result = re.sub(r'\[format:(\w+)\]', '', result)
    result = re.sub(r'%PARSEMODE_(\w+)', '', result)

    if not result:
        result = ''

    return result, mode


def get_msg_parse(text, default_md=True):
    if '[format:html]' in text or '%PARSEMODE_HTML' in text:
        return 'html'
    elif '[format:none]' in text or '%PARSEMODE_NONE' in text:
        return 'none'
    elif '[format:md]' in text or '%PARSEMODE_MD' in text:
        return 'md'
    else:
        if not default_md:
            return None
        return 'md'


def get_reply_msg_btns_text(message):
    text = ''
    for column in message.reply_markup.inline_keyboard:
        btn_num = 0
        for btn in column:
            btn_num += 1
            if btn_num > 1:
                text += "\n[{}](buttonurl:{}:same)".format(
                    btn['text'], btn['url']
                )
            else:
                text += "\n[{}](buttonurl:{})".format(
                    btn['text'], btn['url']
                )
    return text


def get_msg_file(message):
    if 'sticker' in message:
        return {'id': message.sticker.file_id, 'type': 'sticker'}
    elif 'photo' in message:
        return {'id': message.photo[1].file_id, 'type': 'photo'}
    elif 'document' in message:
        return {'id': message.document.file_id, 'type': 'document'}

    return None


def get_parsed_note_list(message, split_args=1):

    note = {}
    if "reply_to_message" in message:
        # Get parsed reply msg text
        text, note['parse_mode'] = get_parsed_msg(message.reply_to_message)
        # Get parsed origin msg text
        text += ' '
        to_split = ''.join([" " + q for q in get_args(message)[:split_args]])
        if not to_split:
            to_split = ' '
        text += get_parsed_msg(message)[0].partition(message.get_command() + to_split)[2][1:]
        # Set parse_mode if origin msg override it
        if mode := get_msg_parse(message.text, default_md=False):
            note['parse_mode'] = mode

        # Get message keyboard
        if 'reply_markup' in message.reply_to_message and 'inline_keyboard' in message.reply_to_message.reply_markup:
            text += get_reply_msg_btns_text(message.reply_to_message)

        # Check on attachment
        if msg_file := get_msg_file(message.reply_to_message):
            note['file'] = msg_file
    else:
        text, note['parse_mode'] = get_parsed_msg(message)
        to_split = ''.join([" " + q for q in get_args(message)[:split_args]])
        if not to_split:
            to_split = ' '
        text = text.partition(message.get_command() + to_split)[2]

        # Check on attachment
        if msg_file := get_msg_file(message):
            note['file'] = msg_file

    # Preview
    if 'text' in note and '$PREVIEW' in note['text']:
        note['preview'] = True
    text = re.sub(r'%PREVIEW', '', text)

    if text.replace(' ', ''):
        note['text'] = text

    return note


async def t_unparse_note_item(message, db_item, chat_id, noformat=None, event=None):
    text = db_item['text'] if 'text' in db_item else ""

    file_id = None
    preview = None

    if 'file' in db_item:
        file_id = db_item['file']['id']

    if noformat:
        markup = None
        if 'parse_mode' not in db_item or db_item['parse_mode'] == 'none':
            text += '\n%PARSEMODE_NONE'
        elif db_item['parse_mode'] == 'html':
            text += '\n%PARSEMODE_HTML'

        if 'preview' in db_item and db_item['preview']:
            text += '\n%PREVIEW'

        db_item['parse_mode'] = None

    else:
        text, markup = tbutton_parser(chat_id, text)

        if 'parse_mode' not in db_item or db_item['parse_mode'] == 'none':
            db_item['parse_mode'] = None
        elif db_item['parse_mode'] == 'md':
            text = await vars_parser(text, message, chat_id, md=True, event=event)
        elif db_item['parse_mode'] == 'html':
            text = await vars_parser(text, message, chat_id, md=False, event=event)

        if 'preview' in db_item and db_item['preview']:
            preview = True

    return text, {
        'buttons': markup,
        'parse_mode': db_item['parse_mode'],
        'file': file_id,
        'link_preview': preview
    }


def button_parser(chat_id, texts):
    buttons = InlineKeyboardMarkup()
    raw_buttons = re.findall(r'\[(.+?)\]\(button(.+?):(.+?)(:same|)\)', texts)
    text = re.sub(r'\[(.+?)\]\(button(.+?):(.+?)(:same|)\)', '', texts)
    for raw_button in raw_buttons:
        btn = raw_button[1]
        if btn in BUTTONS or btn == 'url':
            if btn == 'url':
                url = raw_button[2]
                if url[0] == '/' and url[1] == '/':
                    url = url[2:]
                t = InlineKeyboardButton(raw_button[0], url=url)
            else:
                t = InlineKeyboardButton(raw_button[0], callback_data=BUTTONS[btn] + f':{chat_id}:{raw_button[2]}')

            if raw_button[3]:
                buttons.insert(t)
            else:
                buttons.add(t)
        else:
            texts += f'\n[{raw_button[0]}]\(button{raw_button[2]})'

    return text, buttons


def tbutton_parser(chat_id, texts):
    buttons = []
    raw_buttons = re.findall(r'\[(.+?)\]\(button(.+?):(.+?)(:same|)\)', texts)
    text = re.sub(r'\[(.+?)\]\(button(.+?):(.+?)(:same|)\)', '', texts)
    for raw_button in raw_buttons:
        btn = raw_button[1]
        if btn in BUTTONS or btn == 'url':
            if btn == 'url':
                url = raw_button[2]
                if url[0] == '/' and url[0] == '/':
                    url = url[2:]
                t = [Button.url(raw_button[0], url)]
            else:
                t = [Button.inline(raw_button[0], BUTTONS[btn] + f':{chat_id}:{raw_button[2]}')]

            if raw_button[3]:
                new = buttons[-1] + t
                buttons = buttons[:-1]
                buttons.append(new)
            else:
                buttons.append(t)
        else:
            text += f'\n[{raw_button[0]}]\(button{raw_button[1]}:{raw_button[2]})'

    if len(buttons) == 0:
        buttons = None

    return text, buttons


async def vars_parser(text, message, chat_id, md=False, event=None):

    if not event:
        event = message

    first_name = html.escape(event.from_user.first_name)
    last_name = html.escape(event.from_user.last_name or "")
    user_id = event.from_user.id
    mention = await get_user_link(user_id, md=md)
    username = '@' + (event.from_user.username or mention)

    chat_id = message.chat.id
    chat_name = html.escape(message.chat.title or 'Local')
    chat_nick = message.chat.username or chat_name
    return text.replace('{first}', first_name) \
               .replace('{last}', last_name) \
               .replace('{fullname}', first_name + " " + last_name) \
               .replace('{id}', str(user_id).replace('{userid}', str(user_id))) \
               .replace('{mention}', mention) \
               .replace('{username}', username) \
               .replace('{chatid}', str(chat_id)) \
               .replace('{chatname}', str(chat_name)) \
               .replace('{chatnick}', str(chat_nick))