#!/usr/bin/env python3
# coding=utf-8

# pip install --upgrade requests google-api-python-client google-auth-httplib2 google-auth-oauthlib

import pickle
import os.path
import base64
import time
from datetime import datetime, timedelta, timezone
import requests
import sys
import traceback
from ast import literal_eval
import logging

from email.parser import Parser
from email.header import decode_header
from email.utils import parseaddr

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from apiclient import errors

# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# 获取gmail授权
def get_credit(credential_json_name, token_file_name):
    creds = None

    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists(token_file_name):
        with open(token_file_name, 'rb') as token:
            creds = pickle.load(token)

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credential_json_name, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the credentials for the next run
        with open(token_file_name, 'wb') as token:
            pickle.dump(creds, token)

    return build('gmail', 'v1', credentials=creds)


# 多gmail账号转换
def get_account(acc):
    # token.pickle:  enovelty  (credentials_jk.json)
    # token.pickle2: hallel@gmail.com (credentials_hallel.json)
  
    service_accounts = {
        'enovelty': {'json': 'credentials.json', 'token': 'token.pickle'},
        'hallel': {'json': 'credentials_hallel.json', 'token': 'token.pickle2'},
    }

    return service_accounts[acc]


# 获取gmail的label名称，以及对应的label id
def get_labels(service):
    output = {}
    results = service.users().labels().list(userId='me').execute()
    labels = results.get('labels', [])
    if not labels:
        print('No labels found.')
    else:
        for label in labels:
            output[label['name']] = label['id']
            # print(label['name'] + ': ' + label['id'])

    return output


# 通过条件查询，获取gmail邮件，用空格分隔不同运算符
# Gmail 中可使用的搜索运算符：https://support.google.com/mail/answer/7190?hl=zh-Hans
def get_messages_by_query(service, query='', label_ids=['INBOX'], user_id='me'):
    try:
        response = service.users().messages().list(userId=user_id,
                                                   labelIds=label_ids,
                                                   q=query).execute()
        messages = []
        if 'messages' in response:
            messages.extend(response['messages']['id'])

        while 'nextPageToken' in response:
            page_token = response['nextPageToken']
            response = service.users().messages().list(userId=user_id, q=query,
                                                       pageToken=page_token).execute()
            messages.extend(response['messages']['id'])

        return messages
    except errors.HttpError as error:
        print('An error occurred: %s' % error)


# 通过lable id获取gmail邮件
def get_messages_by_labels(service, label_ids=[], user_id='me'):
    try:
        response = service.users().messages().list(userId=user_id,
                                                   labelIds=label_ids).execute()
        messages = []
        if 'messages' in response:
            messages.extend(response['messages'])

        while 'nextPageToken' in response:
            page_token = response['nextPageToken']
            response = service.users().messages().list(userId=user_id,
                                                       labelIds=label_ids,
                                                       pageToken=page_token).execute()
            messages.extend(response['messages'])

        return messages
    except errors.HttpError as error:
        print('An error occurred: %s' % error)

# 通过 historyId 检查新邮件
# 返回新邮件 id，没有则返回 []；返回 HistoryId，没有更新则返回 startHistoryId
# start_history_id 不能取 1，我测试返回 404
# maxResults 因为钉钉每个机器人每分钟最多发送 20 条
def check_new_email(service, startHistoryId, user_id='me',
                    historyTypes='messageAdded', labelId='INBOX',
                    maxResults=20):
    try:
        history = (service.users().history().list(userId=user_id,
                                                historyTypes=historyTypes,
                                                startHistoryId=startHistoryId,
                                                labelId=labelId,
                                                maxResults=maxResults).execute())
        changes, history_id = (history['history'], history['historyId']) \
                                if 'history' in history else ([], startHistoryId)
        while 'nextPageToken' in history:
            page_token = history['nextPageToken']
            history = (service.users().history().list(userId=user_id,
                                                historyTypes=historyTypes,
                                                startHistoryId=startHistoryId,
                                                labelId=labelId,
                                                maxResults=maxResults,
                                                pageToken=page_token).execute())
            changes.extend(history['history'])

        messages_ids = []
        # 有新邮件才取 id
        if changes:
            for _ in changes:
                messages_ids.append(_['messages'][0]['id'])

        return (messages_ids, history_id)
    except errors.HttpError as error:
        print ('An error occurred: %s' % error)

# 通过邮件id，获取邮件内容
def get_message(service, msg_id, user_id='me', msg_format='raw'):
    try:
        message = service.users().messages().get(userId=user_id, id=msg_id,
                                                 format=msg_format).execute()
        msg_str = base64.urlsafe_b64decode(message['raw'].encode('ASCII'))
        msg = Parser().parsestr(msg_str.decode('utf-8'))
        
        return msg

    except errors.HttpError as error:
        print('An error occurred: %s' % error)


# 通过邮件id数组，获取邮件数组
def get_messages(service, message_ids):
    output = []

    for message_id in message_ids:
        message = get_message(service, message_id)
        output.append(message)

    return output


# 猜测邮件编码
def guess_charset(msg):
    charset = msg.get_charset()
    if charset is None:
        content_type = msg.get('Content-Type', '').lower()
        pos = content_type.find('charset=')
        if pos >= 0:
            charset = content_type[pos + 8:].strip()
    return charset

# 邮件解码
def decode_str(s):
    value, charset = decode_header(s)[0]
    if charset:
        value = value.decode(charset)
    return value

# 获取邮件主题、发件人信息
def get_info(msg):
    info_dict = {}
    for header in ['Subject', 'From']:
        value = msg.get(header, '')
        if value:
            if header=='Subject':
                value = decode_str(value)
            else:
                hdr, addr = parseaddr(value)
                name = decode_str(hdr)
                value = u'%s <%s>' % (name, addr)
        info_dict[header] = value

    return info_dict

# 发消息到钉钉机器人
# data 里面不能有 "
def send_to_ding(info_dict, access_token, error=False):
    # TODO: linux 下的拼接有问题
    url = 'https://oapi.dingtalk.com/robot/send?access_token={}'.format(access_token)
    logging.info(url)
    headers = {'Content-Type': 'application/json'}
    if error:
        data = '''
        {{
            "msgtype": "markdown",
            "markdown": {{
                "title": "错误",
                "text": "# 错误\n{0}"
            }}
        }}
        '''.format(info_dict.replace('"', '\\"').replace('\n', '  \\n'))
        # JSON 字符串中要对 " 转义为 \"，对换行符转成可见字符，且符合 md 语法
        logging.info(data)
    else:
        data = '''
        {{
            "msgtype": "markdown",
            "markdown": {{
                "title": "{0}",
                "text": "# {0}\n**发件人：**{1}"
            }}
        }}
        '''.format(str(info_dict['Subject']), info_dict['From'])
        print(str(info_dict['Subject']))
    # 直接发 JSON 字符串即可，utf-8 编码
    resp = requests.post(url=url, headers=headers, data=data.encode('utf-8'))
    
    print('\t' + resp.text)

# UTC+8 时间
def get_time():
    dt = datetime.utcnow().replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone(timedelta(hours=8)))
    return(dt)

# 获取收件箱中的未读邮件，发钉钉通知
def main(acc, pull_interval, access_token):
    if os.path.exists('history_id') == False:
        print('请创建 history_id 文件')
    if os.path.exists('access_token') == False:
        print('请创建并填写 access_token 文件')
        if os.path.getsize('access_token') == 0:
            print('请填写 access_token 文件')
    account = get_account(acc)
    service = get_credit(account['json'], account['token'])

    old_history_id = ''
    # 第一次使用，取最新一条邮件的 historyId
    if os.path.getsize('history_id') == 0:
        msg_id = service.users().messages().list(userId='me',
                                                 labelIds='INBOX',
                                                 maxResults=1).execute()
        old_history_id = service.users().messages().get(userId='me',
                                                    id=msg_id['messages'][0]['id'],
                                                    format='minimal'
                                                    ).execute()['historyId']
        with open('history_id', 'w') as f:
            f.write(old_history_id)
    else:
        # 已推送的最新 history_id 存在文件中
        with open('history_id', 'r') as f:
            old_history_id = f.read()

    while True:
        print(get_time())
        messages_ids, history_id = check_new_email(service, old_history_id)
        # 未读且未推送的邮件，调用钉钉机器人
        if history_id != old_history_id:
            messages = get_messages(service, messages_ids)
            for m in messages:
                msg = get_info(m)
                send_to_ding(msg, access_token)
            print()
            with open('history_id', 'w') as f:
                f.write(history_id)
            old_history_id = history_id
        else:
            print('\tNo new email.\n')

        time.sleep(pull_interval)

if __name__ == '__main__':
    # logging.basicConfig(level=logging.INFO)
    logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.CRITICAL)

    with open('access_token', 'r') as f:
        # access_token 长度为 64 字节，不填写长度在 linux 下会多读一个 \n
        access_token = f.read(64)

    try:
        main('enovelty', float(sys.argv[1]), access_token)
    # 运行出错时，推送到钉钉
    except BaseException as e:
        # 输出完整 traceback
        print(get_time())
        traceback.print_exc()
        send_to_ding(traceback.format_exc(), access_token, True)