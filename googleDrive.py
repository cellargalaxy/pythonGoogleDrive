# -*- coding: utf-8 -*-

from __future__ import print_function

import json
import os
import threading
from time import sleep

import httplib2
import requests

from apiclient import discovery
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from oauth2client import client
from oauth2client import tools
from oauth2client.file import Storage
from werkzeug.serving import run_simple
from werkzeug.wrappers import Request, Response

from jsonrpc import JSONRPCResponseManager, dispatcher

try:
    import argparse

    flags = argparse.ArgumentParser(parents=[tools.argparser]).parse_args()
except ImportError:
    flags = None

THREAD_POOL_SIZE = 2
JSON_RPC_HOST = '0.0.0.0'
JSON_RPC_PORT = 6600
SAVE_FOLDER_PATH = '/home/cellargalaxy'

SCOPES = 'https://www.googleapis.com/auth/drive'
TEMP_FILE_NAME = '.temp'
APPLICATION_NAME = 'pythonGoogleDrive'
CLIENT_JSON_FILE_NAME = '.pythonGoogleDrive-client.json'
FOLDER_MINE_TYPE = 'application/vnd.google-apps.folder'
FILE_INFO = 'id, name, mimeType, parents, size, webViewLink, webContentLink'
MARK_FILE_NAME = 'pythonGoogleDrive.txt'


class GoogleDiverAPI(object):
    def __init__(self):
        self.service = self.get_service()
        self.root_id = self.get_root_id()

    def get_temp_file(self):
        """
        获取临时文件
        :return: 无返回
        """
        request = requests.get('http://www.cellargalaxy.top/pythonGoogleDiver.json')
        with open(TEMP_FILE_NAME, 'w') as file:
            file.write(request.json())

    def delete_temp_file(self):
        """
        删除临时文件
        :return: 无返回
        """
        os.remove(TEMP_FILE_NAME)

    def get_credentials(self):
        """
        通过密匙json获取客户的登录权限并生成资格证书
        Returns: 资格证书对象
        """
        home_dir = os.path.expanduser('~')
        credential_path = os.path.join(home_dir, CLIENT_JSON_FILE_NAME)

        # 这个应该意思是谷歌的应用商店对象
        store = Storage(credential_path)
        credentials = store.get()
        # 如果获取证书失败或者证书失效
        if not credentials or credentials.invalid:
            self.get_temp_file()
            flow = client.flow_from_clientsecrets(TEMP_FILE_NAME, SCOPES)
            flow.user_agent = APPLICATION_NAME
            self.delete_temp_file()
            if flags:
                credentials = tools.run_flow(flow, store, flags)
            else:  # Needed only for compatibility with Python 2.6
                credentials = tools.run(flow, store)
            print('客户证书路径：' + credential_path)
        return credentials

    def get_service(self):
        """
        获取谷歌硬盘服务对象
        :return: 谷歌硬盘服务对象
        """
        credentials = self.get_credentials()
        http = credentials.authorize(httplib2.Http())
        service = discovery.build('drive', 'v3', http=http)
        return service

    def get_root_id(self):
        """
        获取根目录id
        :return: 目录id
        """
        try:
            if self.root_id:
                return self.root_id
        except AttributeError:
            pass

        mark_files = self.search_files_by_name(MARK_FILE_NAME)
        if not mark_files:
            with open(MARK_FILE_NAME, 'w') as file:
                file.write('这是' + APPLICATION_NAME + '的标记文件。')
            mark_file = self.upload_file(MARK_FILE_NAME)
            os.remove(MARK_FILE_NAME)
        else:
            mark_file = mark_files[0]

        folder_id = mark_file['id']
        while True:
            parent_folder_id = self.get_parent_folder(folder_id)
            if parent_folder_id == folder_id:
                break
            else:
                folder_id = parent_folder_id
        return folder_id

    def get_file_list(self, folder_id=None):
        """
        获取某个文件夹下全部文件序列，默认在根目录
        :param folder_id: 某个文件夹的id
        :return: 某个文件夹下全部文件序列
        """
        if not folder_id:
            folder_id = self.get_root_id()
        files = []
        page_token = None
        while True:
            response = self.service.files().list(q="'" + folder_id + "' in parents and trashed = false",
                                                 fields='nextPageToken, files(' + FILE_INFO + ')',
                                                 pageToken=page_token).execute()
            for file in response.get('files', []):
                files.append(file)
            page_token = response.get('nextPageToken', None)
            if page_token is None:
                break
        return files

    def search_files_by_name(self, file_name):
        """
        通过文件名寻找文件
        :param file_name: 文件名
        :return: 包含文件名的文件对象序列
        """
        files = []
        page_token = None
        while True:
            response = self.service.files().list(q="name contains '" + file_name + "' and trashed = false",
                                                 fields='nextPageToken, files(' + FILE_INFO + ')',
                                                 pageToken=page_token).execute()
            for file in response.get('files', []):
                files.append(file)
            page_token = response.get('nextPageToken', None)
            if page_token is None:
                break
        return files

    def search_file_by_id(self, file_id):
        return self.service.files().get(fileId=file_id,
                                        fields=FILE_INFO).execute()

    def get_parent_folder(self, file_id):
        """
        获取文件或者文件夹的父文件夹id
        :param file_id: 文件或者文件夹id
        :return: 父文件夹id
        """
        file = self.search_file_by_id(file_id)
        if not file:
            return None
        if file.get('parents') and file.get('parents')[0]:
            return file.get('parents')[0]
        else:
            return file_id

    def create_folder(self, folder_name, parent_folder_id=None):
        """
        创建一个文件夹，默认在根目录下
        :param folder_name: 文件夹名字
        :param folder_id: 文件夹所在文件夹
        :return: 新建文件夹对象
        """
        if not parent_folder_id:
            parent_folder_id = self.get_root_id()
        folder_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_folder_id]
        }
        folder = self.service.files().create(body=folder_metadata,
                                             fields=FILE_INFO).execute()
        return folder

    def upload_file(self, file_path, folder_id=None, file_name=None):
        """
        上传文件，上传的文件名默认为本地文件名
        :param file_path: 文件的本地路径
        :param folder_id: 上传到哪个文件夹的id,默认为根目录
        :param file_name: 重命名上传文件，默认原名
        :return: 成功上传的文件对象
        """
        if not folder_id:
            folder_id = self.get_root_id()
        if not file_name:
            file_name = os.path.basename(file_path)
        file_metadata = {
            'name': file_name,
            'parents': [folder_id]
        }
        media = MediaFileUpload(file_path, resumable=True)

        file = self.service.files().create(body=file_metadata,
                                           media_body=media,
                                           fields=FILE_INFO).execute()
        return file

    def download_file_by_id(self, file_id, save_folder_path, status_func, file_name=None):
        """
        下载文件
        :param file_id: 下载文件的id
        :param save_file_path: 下载到本地的路径
        :param status_func: 下载状态调用方法
        :param file_name: 命名下载文件，默认原名
        :return: 无返回
        """
        file = self.search_file_by_id(file_id)
        self.download_file(file, save_folder_path, status_func, file_name)

    def download_file(self, file, save_folder_path, status_func, file_name=None):
        """
        下载文件
        :param file: 下载文件的对象
        :param save_file_path: 下载到本地的路径
        :param status_func: 下载状态调用方法
        :param file_name: 命名下载文件，默认原名
        :return: 无返回
        """
        if not os.path.exists(save_folder_path):
            os.makedirs(save_folder_path)
        if not file_name:
            file_name = file['name']

        save_file = open(save_folder_path + '/' + file_name, 'wb')
        request = self.service.files().get_media(fileId=file['id'])
        downloader = MediaIoBaseDownload(save_file, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            status_func(file, status, done)

    def is_folder_by_id(self, file_id):
        """
        某个文件是否是文件夹
        :param file_id: 文件id
        :return: 是否是文件夹
        """
        file = self.search_file_by_id(file_id)
        return self.is_folder(file)

    def is_folder(self, file):
        """
        某个文件是否是文件夹
        :param file: 文件对象
        :return: 是否是文件夹
        """
        if file['mimeType'] == FOLDER_MINE_TYPE:
            return True
        else:
            return False

    def move_file(self, file_id, folder_id):
        """
        移动文件到另一个文件夹下
        :param file_id: 文件或文件夹id
        :param folder_id: 目的地文件夹
        :return: 移动后的文件对象
        """
        file = self.service.files().get(fileId=file_id, fields='parents').execute()
        previous_parents = ",".join(file.get('parents'))
        file = self.service.files().update(fileId=file_id,
                                           addParents=folder_id,
                                           removeParents=previous_parents,
                                           fields=FILE_INFO).execute()
        return file

    def print_files(self, files):
        for file in files:
            try:
                print('%s\t(%s)\t类型:%s\t%sK\tparents:%s\t浏览链接:%s\t下载链接:%s' % (
                    file['name'], file['id'], file['mimeType'], file['size'], file['parents'], file['webViewLink'],
                    file['webContentLink']))
            except KeyError:
                print('%s\t(%s)\t类型:%s\tparents:%s\t浏览链接:%s' % (
                    file['name'], file['id'], file['mimeType'], file['parents'], file['webViewLink']))


class GoogleDiverClient(GoogleDiverAPI):
    def __init__(self):
        GoogleDiverAPI.__init__(self)
        self.wait_works = []
        self.doing_works = []
        self.done_works = []
        self.threads = []
        self.now_id = self.get_root_id()
        self.wait_works_lock = threading.Lock()
        self.doing_works_lock = threading.Lock()
        self.done_works_lock = threading.Lock()
        self.thread_pool_lock = threading.Lock()

    def create_thread(self):
        """
        创建新增一个工作线程
        :return:
        """
        self.thread_pool_lock.acquire()
        try:
            if len(self.threads) == 0 or (len(self.wait_works) > 1 and len(self.threads) < THREAD_POOL_SIZE):
                thread = WorkThread(self)
                self.threads.append(thread)
                thread.start()
        finally:
            self.thread_pool_lock.release()

    def remove_thread(self, thread):
        """
        当工作线程死亡时移除出线程队列
        :param thread: 死亡的线程
        :return:
        """
        i = 0
        self.thread_pool_lock.acquire()
        try:
            for th in self.threads:
                if th == thread:
                    self.threads.pop(i)
                    return
                i = i + 1
        finally:
            self.thread_pool_lock.release()

    def create_and_add_wait_work(self, is_download, path, id):
        """
        往工作等待队列添加工作
        :param is_download: 是下载还是上传
        :param path: 本地路径
        :param id: 文件id
        :return: 如何工作重复返回None，否则成功插入到工作等待队列，返回工作对象
        """
        self.wait_works_lock.acquire()
        try:
            for work in self.wait_works:
                if work.is_download == is_download and work.path == path and work.id == id:
                    return None
        finally:
            self.wait_works_lock.release()

        self.doing_works_lock.acquire()
        try:
            for work in self.doing_works:
                if work.is_download == is_download and work.path == path and work.id == id:
                    return None
        finally:
            self.doing_works_lock.release()

        self.wait_works_lock.acquire()
        try:
            work = Work(is_download, path, id)
            self.wait_works.append(work)
        finally:
            self.wait_works_lock.release()

        self.create_thread()
        return work

    def remove_wait_work(self, is_download, path, id):
        """
        在等待队列删除任务
        :param is_download:
        :param path:
        :param id:
        :return: 删除是否成功
        """
        i = 0
        self.wait_works_lock.acquire()
        try:
            for work in self.wait_works:
                if work.is_download == is_download and work.path == path and work.id == id:
                    self.wait_works.pop(i)
                    return True
                i = i + 1
            return False
        finally:
            self.wait_works_lock.release()

    def poll_wait_work(self):
        """
        从等待队列中获取工作
        :return: 工作对象
        """
        self.wait_works_lock.acquire()
        try:
            if len(self.wait_works) > 0:
                return self.wait_works.pop(0)
            return None
        finally:
            self.wait_works_lock.release()

    def add_doing_work(self, work):
        """
        往正在工作队列中添加工作
        :param work: 添加的工作
        :return:
        """
        self.doing_works_lock.acquire()
        try:
            print('add_doing_work')
            print(self.doing_works)
            print()
            self.doing_works.append(work)
        finally:
            self.doing_works_lock.release()

    def remove_doing_work(self, work):
        """
        从正在工作队列中删除已完成的工作
        :param work: 已完成的工作
        :return:
        """
        i = 0
        self.doing_works_lock.acquire()
        try:
            for w in self.doing_works:
                if w == work:
                    self.doing_works.pop(i)
                    return True
                i = i + 1
            return False
        finally:
            self.doing_works_lock.release()

    def add_done_work(self, work):
        """
        添加一个已完成工作到完成队列
        :param work:
        :return:
        """
        self.done_works_lock.acquire()
        try:
            self.done_works.append(work)
        finally:
            self.done_works_lock.release()

    def remove_done_work(self, is_download, path, id):
        """
        从完成队列中删除一个已完成工作
        :param is_download:
        :param path:
        :param id:
        :return:
        """
        i = 0
        self.done_works_lock.acquire()
        try:
            for work in self.done_works:
                if work.is_download == is_download and work.path == path and work.id == id:
                    self.done_works.pop(i)
                    return True
                i = i + 1
            return False
        finally:
            self.done_works_lock.release()

    def do_work(self, main_client, work, status_func):
        """
        执行工作
        :param work:
        :param status_func:
        :return:
        """
        if work.is_download:
            self.do_download_work(main_client, work.id, work.path, status_func)
        else:
            self.do_upload_work(main_client, work.path, work.id)

    def do_upload_work(self, main_client, path, id):
        """
        执行上传工作，如果上传是文件，则上传，如果是文件夹，先交由upload_folder_to_works拆散成单个文件，并添加到等待队列
        :param path: 上传本地路径
        :param id: 上传到文件夹的id
        :return:
        """
        try:
            if os.path.isdir(path):
                self.upload_folder_to_works(main_client=main_client, folder_path=path, folder_id=id)
            else:
                print('开始上传', path)
                while True:
                    try:
                        self.upload_file(file_path=path, folder_id=id)
                        break
                    except Exception as e:
                        print(e)
                        if os.path.getsize(path) == 0:
                            print('上传失败，是空文件，上传会报400 bad request，无法上传', path)
                            break
                        print('上传失败，再次尝试上传', path)
                print('上传完成', path)
        except Exception as e:
            print(e)
            print('上传失败', path, id)

    def do_download_work(self, main_client, id, path, status_func):
        """
        执行下载工作，如果下载是文件则直接下载，否则交给download_folder_to_works拆散成单个文件，并添加到等待队列
        :param id: 下载的id
        :param path: 保存的本地路径
        :param status_func: 监控方法
        :return:
        """
        try:
            if self.is_folder_by_id(id):
                self.download_folder_to_works(main_client=main_client, folder_id=id, save_folder_path=path)
            else:
                file = self.search_file_by_id(id)
                print('开始下载', file['name'], file['id'])
                while True:
                    try:
                        self.download_file(file=file, save_folder_path=path, status_func=status_func)
                        break
                    except Exception as e:
                        print(e)
                        print('下载失败，再次尝试下载', file['name'], file['id'])
                print('下载完成', file['name'], file['id'])
        except Exception as e:
            print(e)
            print('下载失败', id, path)

    def upload_folder_to_works(self, main_client, folder_path, folder_id=None):
        """
        把文件夹拆散成单个文件，并创建对应的文件夹得到其id，分配到各个文件上传，并添加到等待队列
        :param folder_path: 上传的文件夹
        :param folder_id: 保存到文件夹的id
        :return: 无返回
        """
        if not os.path.exists(folder_path):
            return
        if not folder_id:
            folder_id = self.get_root_id()
        folder = self.create_folder(os.path.basename(folder_path), folder_id)
        file_names = os.listdir(folder_path)
        for file_name in file_names:
            file_path = folder_path + '/' + file_name
            if os.path.isdir(file_path):
                self.upload_folder_to_works(main_client, file_path, folder['id'])
            else:
                if not main_client.create_and_add_wait_work(False, file_path, folder['id']):
                    print('上传任务已经在队列中', file_path, folder['name'], folder['id'])
                else:
                    print('添加上传任务', file_path, folder['name'], folder['id'])

    def download_folder_to_works(self, main_client, folder_id, save_folder_path):
        """
        下载文件夹，将下载的文件夹拆散成单个文件，并设置对应的保存路径，并添加到等待队列
        :param folder_id: 下载文件夹的id
        :param save_folder_path: 保存到的本地路径
        :param status_func: 下载状态调用方法
        :return:
        """
        folder = self.search_file_by_id(folder_id)
        files = self.get_file_list(folder_id)
        for file in files:
            if self.is_folder(file):
                self.download_folder_to_works(main_client, file['id'], save_folder_path + '/' + folder['name'])
            else:
                if not main_client.create_and_add_wait_work(True, save_folder_path + '/' + folder['name'], file['id']):
                    print('下载任务已在队列中', file['name'], file['id'], save_folder_path + '/' + folder['name'])
                else:
                    print('添加下载队列', file['name'], file['id'], save_folder_path + '/' + folder['name'])

                    # API start ---------------------------------------------------------------

    def upload(self, path, folder_id=None):
        """
        添加上传任务
        :param path: 上传的本地路径
        :param folder_id: 保存到文件夹的id
        :return: 任务添加是否成功
        """
        if not os.path.exists(path):
            print('目录不存在', path)
            return False
        if self.create_and_add_wait_work(False, path, folder_id):
            print('添加上传任务', path, folder_id)
            return True
        else:
            print('上传任务已经在队列中', path, folder_id)
            return False

    def download(self, id, save_folder_path):
        """
        添加下载任务
        :param id: 下载的文件夹或者文件的id
        :param save_folder_path: 保存到本地目录
        :return: 任务添加是否成功
        """
        if self.create_and_add_wait_work(True, save_folder_path, id):
            print('添加下载队列', id, save_folder_path)
            return True
        else:
            print('下载任务已在队列中', id, save_folder_path)
            return False

    def delete_wait_work(self, is_download, path, id):
        """
        从等待队列中取消任务
        :param is_download: 任务是下载还是上传
        :param path: 本地路径
        :param id: 文件或者文件夹id
        :return: 取消是否成功
        """
        return self.remove_wait_work(is_download, path, id)

    def delete_done_work(self, is_download, path, id):
        """
        从完成队列中删除任务
        :param is_download: 任务是下载还是上传
        :param path: 本地路径
        :param id: 文件或者文件夹id
        :return: 删除是否成功
        """
        return self.remove_done_work(is_download, path, id)

    def get_now_file_list(self):
        """
        返回当前文件夹的文件列表json
        :return: 前文件夹的文件列表json
        """
        return self.get_file_list(self.now_id)

    def goto_parent_folder(self):
        """
        返回父目录
        :return: 父目录下全部文件夹和文件json
        """
        print('self.now_id', self.now_id)
        self.now_id = self.get_parent_folder(self.now_id)
        return self.get_file_list(self.now_id)

    def goto_child_folder(self, child_folder_id):
        """
        进入子目录
        :param child_folder_id: 子目录的id
        :return: 子目录下全部文件夹和文件json
        """
        self.now_id = child_folder_id
        return self.get_file_list(self.now_id)

    def get_json_wait_works(self):
        """
        获取wait_works的json
        :return: wait_works的json
        """
        list = []
        self.wait_works_lock.acquire()
        try:
            for work in self.wait_works:
                list.append(work.to_map())
            return json.dumps(list)
        finally:
            self.wait_works_lock.release()

    def get_json_doing_works(self):
        """
        获取doing_works的json
        :return: doing_works的json
        """
        list = []
        self.doing_works_lock.acquire()
        try:
            for work in self.doing_works:
                list.append(work.to_map())
            return json.dumps(list)
        finally:
            self.doing_works_lock.release()

    def get_json_done_works(self):
        """
        获取done_works的json
        :return: done_works的json
        """
        list = []
        self.done_works_lock.acquire()
        try:
            for work in self.done_works:
                list.append(work.to_map())
            return json.dumps(list)
        finally:
            self.done_works_lock.release()


# API end ---------------------------------------------------------------


class Work(object):
    def __init__(self, is_download, path, id):
        self.is_download = is_download
        self.path = path
        self.id = id
        self.progress = 0
        self.done = False
        self.file_name = None

    def to_map(self):
        return {'is_download': self.is_download, 'path': self.path, 'id': self.id, 'progress': self.progress,
                'done': self.done, 'file_name': self.file_name}


class WorkThread(threading.Thread):
    def __init__(self, main_client):
        threading.Thread.__init__(self)
        self.main_client = main_client
        self.thread_client = GoogleDiverClient()
        self.work = None

    def run(self):
        none_count = 0
        while none_count < 10:
            work = self.main_client.poll_wait_work()
            if not work:
                none_count = none_count + 1
                self.work = None
                sleep(1)
            else:
                self.work = work
                none_count = 0
                self.main_client.add_doing_work(work)
                self.thread_client.do_work(self.main_client, work, self.status_func)
                self.main_client.remove_doing_work(work)
                self.main_client.add_done_work(work)
        self.main_client.remove_thread(self)

    def status_func(self, file, status, done):
        if self.work:
            self.work.progress = int(status.progress() * 100)
            self.work.done = done
            self.work.file_name = file['name']
            print(file['name'], "%d%%." % int(status.progress() * 100), done)


class GoogleDiverClientDaemon(object):
    def __init__(self):
        self.googleDiverClient = GoogleDiverClient()
        self.manager = JSONRPCResponseManager()

    def upload(self, path):
        print('上传文件', path)
        return self.googleDiverClient.upload(path=path, folder_id=self.googleDiverClient.now_id)

    def download(self, **map):
        print('下载', map['id'], map['save_folder_path'])
        return self.googleDiverClient.download(id=map['id'], save_folder_path=map['save_folder_path'])

    def delete_wait_work(self, **map):
        print('取消wait', map['is_download'], map['path'], map['id'])
        return self.googleDiverClient.delete_wait_work(is_download=map['is_download'], path=map['path'], id=map['id'])

    def delete_done_work(self, **map):
        print('删除done', map['is_download'], map['path'], map['id'])
        return self.googleDiverClient.delete_done_work(is_download=map['is_download'], path=map['path'], id=map['id'])

    def get_now_file_list(self):
        print('刷新')
        return self.googleDiverClient.get_now_file_list()

    def goto_parent_folder(self):
        print('父文件夹')
        return self.googleDiverClient.goto_parent_folder()

    def goto_child_folder(self, child_folder_id):
        print('子文件夹', child_folder_id)
        return self.googleDiverClient.goto_child_folder(child_folder_id=child_folder_id)

    def get_json_wait_works(self):
        print('wait_works')
        return self.googleDiverClient.get_json_wait_works()

    def get_json_doing_works(self):
        print('doing_works')
        return self.googleDiverClient.get_json_doing_works()

    def get_json_done_works(self):
        print('done_works')
        return self.googleDiverClient.get_json_done_works()

    @Request.application
    def application(self, request):
        response = self.manager.handle(request.get_data(cache=False, as_text=True), dispatcher)
        # print(response.json)
        # print()
        if 'code": -32700' in response.json:
            return Response(INDEX_HTML, mimetype='text/html')
        else:
            return Response(response.json, mimetype='application/json')

    def daemon(self):
        dispatcher['upload'] = self.upload
        dispatcher['download'] = self.download
        dispatcher['delete_wait_work'] = self.delete_wait_work
        dispatcher['delete_done_work'] = self.delete_done_work
        dispatcher['get_now_file_list'] = self.get_now_file_list
        dispatcher['goto_parent_folder'] = self.goto_parent_folder
        dispatcher['goto_child_folder'] = self.goto_child_folder
        dispatcher['get_json_wait_works'] = self.get_json_wait_works
        dispatcher['get_json_doing_works'] = self.get_json_doing_works
        dispatcher['get_json_done_works'] = self.get_json_done_works
        print('监控地址', 'http://' + JSON_RPC_HOST + ':' + str(JSON_RPC_PORT) + '/jsonrpc')
        run_simple(JSON_RPC_HOST, JSON_RPC_PORT, self.application)


INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>pythonGoogleDiver Web 控制台</title>
    <script type="text/javascript" src="https://code.jquery.com/jquery-3.2.1.min.js"></script>
    <style>
        tr{
            background-color: lightgreen
        }
        .name{
            color: blue;
            text-decoration: underline;
        }
    </style>
</head>
<body style="background-color: antiquewhite">

<table>
    <tr>
        <td>下载保存路径:<input type="text" id="download_file_path" value=\"""" + SAVE_FOLDER_PATH + """\"></td>
        <td>上传文件路径:<input type="text" id="upload_file_path"></td>
        <td><button onclick="upload()">upload</button></td>
    </tr>
</table>

<br><br>

<table>
    <tr>
        <td>文件列表</td>
        <td><button onclick="flush()">flush-list</button></td>
        <td><button onclick="parent()">parent-folder</button></td>
    </tr>
</table>
<table id="file_list" style="text-align: center;width: 100%">
    <tr>
        <td>name</td>
        <td>id</td>
        <td>mimeType</td>
        <td>webViewLink</td>
        <td>download</td>
    </tr>
</table>

<br><br>

<table>
    <tr>
        <td>正在下载</td>
        <td><button onclick="doing()">flush-doing</button></td>
    </tr>
</table>
<table id="doing_list" style="text-align: center;width: 100%">
    <tr>
        <td>is_download</td>
        <td>path</td>
        <td>id</td>
        <td>progress</td>
        <td>done</td>
        <td>file_name</td>
    </tr>
</table>

<br><br>

<table>
    <tr>
        <td>下载完成</td>
        <td><button onclick="done()">flush-done</button></td>
    </tr>
</table>
<table id="done_list" style="text-align: center;width: 100%">
    <tr>
        <td>is_download</td>
        <td>path</td>
        <td>id</td>
        <td>progress</td>
        <td>done</td>
        <td>file_name</td>
        <td>删除</td>
    </tr>
</table>

<br><br>

<table>
    <tr>
        <td>等待下载</td>
        <td><button onclick="wait()">flush-wait</button></td>
    </tr>
</table>
<table id="wait_list" style="text-align: center;width: 100%">
    <tr>
        <td>is_download</td>
        <td>path</td>
        <td>id</td>
        <td>progress</td>
        <td>done</td>
        <td>file_name</td>
        <td>取消</td>
    </tr>
</table>
</body>
<script>

</script>

<script>
function upload() {
    upload_path=$('#upload_file_path').val()
    if (!confirm("确认上传?:" + upload_path)) {
        return
    }
    $.ajax({
        url: '',
        type: 'post',
        data: '{"method": "upload","params": ["'+upload_path+'"],"jsonrpc": "2.0","id": 0}',
        contentType: "application/x-www-form-urlencoded",
        dataType: "json",

        error: function () {
            alert("upload,网络错误!");
        },
        success: function (data) {
            if('result' in data){
                if(data['result']){
                    alert('成功提交上传：'+upload_path)
                }else{
                    alert('失败提交上传：'+upload_path)
                }
                return
            }
            if('error' in data){
                alert('失败提交上传：'+upload_path+' '+JSON.stringify(data))
                return
            }
            alert("未知响应：" + JSON.stringify(data))
        }
    })
}
function download(file_id,file_name) {
    save_folder_path=$('#download_file_path').val()
    if (!confirm("确认下载?:" + file_id+' '+file_name+' '+save_folder_path)) {
        return
    }
    $.ajax({
        url: '',
        type: 'post',
        data: '{"method": "download", "params": {"id": "'+file_id+'", "save_folder_path": "'+save_folder_path+'"},"jsonrpc": "2.0","id": 1}',
        contentType: "application/x-www-form-urlencoded",
        dataType: "json",

        error: function () {
            alert("download,网络错误!");
        },
        success: function (data) {
            if('result' in data){
                if(data['result']){
                    alert('成功提交下载：' + file_id+' '+file_name+' '+save_folder_path)
                }else{
                    alert('失败提交下载：' + file_id+' '+file_name+' '+save_folder_path)
                }
                return
            }
            if('error' in data){
                alert('失败提交下载：' + file_id+' '+file_name+' '+save_folder_path+' '+JSON.stringify(data))
                return
            }
            alert("未知响应：" + JSON.stringify(data))
        }
    })
}
function delete_wait(is_download,path,id){
    if (!confirm("确认删除?:" + is_download+' '+path+' '+id)) {
        return
    }
    $.ajax({
        url: '',
        type: 'post',
        data: '{"method": "delete_wait_work","params": {"is_download": '+is_download+', "path": "'+path+'", "id": "'+id+'"},"jsonrpc": "2.0","id": 2}',
        contentType: "application/x-www-form-urlencoded",
        dataType: "json",

        error: function () {
            alert("download,网络错误!");
        },
        success: function (data) {
            if('result' in data){
                if(data['result']){
                    alert('成功取消任务：'+is_download+' '+path+' '+id)
                }else{
                    alert('失败取消任务：'+is_download+' '+path+' '+id)
                }
                return
            }
            if('error' in data){
                alert('失败取消任务：'+is_download+' '+path+' '+id+' '+JSON.stringify(data))
                return
            }
            alert("未知响应：" + JSON.stringify(data))
        }
    })
}
function delete_done(is_download,path,id){
    if (!confirm("确认删除?:" + is_download+' '+path+' '+id)) {
        return
    }
    $.ajax({
        url: '',
        type: 'post',
        data: '{"method": "delete_done_work","params": {"is_download": '+is_download+', "path": "'+path+'", "id": "'+id+'"},"jsonrpc": "2.0","id": 3}',
        contentType: "application/x-www-form-urlencoded",
        dataType: "json",

        error: function () {
            alert("download,网络错误!");
        },
        success: function (data) {
            if('result' in data){
                if(data['result']){
                    alert('成功删除任务：'+is_download+' '+path+' '+id)
                }else{
                    alert('失败删除任务：'+is_download+' '+path+' '+id)
                }
                return
            }
            if('error' in data){
                alert('失败删除任务：'+is_download+' '+path+' '+id+' '+JSON.stringify(data))
                return
            }
            alert("未知响应：" + JSON.stringify(data))
        }
    })
}
function flush() {
    save_folder_path=$('#download_file_path').val()
    html=''
    html+='<tr>'
    html+='<td>name</td>'
    html+='<td>id</td>'
    html+='<td>mimeType</td>'
    html+='<td>webViewLink</td>'
    html+='<td>download</td>'
    html+='</tr>'
    $('#file_list').html(html)
    $.ajax({
        url: '',
        type: 'post',
        data: '{"method": "get_now_file_list","jsonrpc": "2.0","id": 4}',
        contentType: "application/x-www-form-urlencoded",
        dataType: "json",

        error: function () {
            $('#file_list').html(html+'<tr><td>网络错误!</td></tr>')
        },
        success: function (data) {
            if('result' in data){
                array = JSON.parse(JSON.stringify(data['result']))
                for (var i in array) {
                    html+='<tr>'
                    if(array[i]['mimeType']=='application/vnd.google-apps.folder'){
                        html+='<td class="name" onclick="child(\\\''+array[i]['id']+'\\\')">'+array[i]['name']+'</td>'
                    }else{
                        html+='<td>'+array[i]['name']+'</td>'
                    }
                    html+='<td>'+array[i]['id']+'</td>'
                    html+='<td>'+array[i]['mimeType']+'</td>'
                    html+='<td><a target= "_blank" href="'+array[i]['webViewLink']+'">浏览链接</a></td>'
                    html+='<td><button onclick="download(\\\''+array[i]['id']+'\\\',\\\''+array[i]['name']+'\\\')">download</button></td>'
                    html+='</tr>'
                }
                $('#file_list').html(html)
                return
            }
            if('error' in data){
                $('#file_list').html(html+'<tr><td>刷新失败</td><td>'+JSON.stringify(data)+'</td></tr>')
                return
            }
            $('#file_list').html(html+'<tr><td>未知响应</td><td>'+JSON.stringify(data)+'</td></tr>')
        }
    })
}
function parent() {
    save_folder_path=$('#download_file_path').val()
    html=''
    html+='<tr>'
    html+='<td>name</td>'
    html+='<td>id</td>'
    html+='<td>mimeType</td>'
    html+='<td>webViewLink</td>'
    html+='<td>download</td>'
    html+='</tr>'
    $('#file_list').html(html)
    $.ajax({
        url: '',
        type: 'post',
        data: '{"method": "goto_parent_folder","jsonrpc": "2.0","id": 5}',
        contentType: "application/x-www-form-urlencoded",
        dataType: "json",

        error: function () {
            alert("parent网络错误!");
        },
        success: function (data) {
            if('result' in data){
                array = JSON.parse(JSON.stringify(data['result']))
                for (var i in array) {
                    html+='<tr>'
                    if(array[i]['mimeType']=='application/vnd.google-apps.folder'){
                        html+='<td class="name" onclick="child(\\\''+array[i]['id']+'\\\')">'+array[i]['name']+'</td>'
                    }else{
                        html+='<td>'+array[i]['name']+'</td>'
                    }
                    html+='<td>'+array[i]['id']+'</td>'
                    html+='<td>'+array[i]['mimeType']+'</td>'
                    html+='<td><a target= "_blank" href="'+array[i]['webViewLink']+'">浏览链接</a></td>'
                    html+='<td><button onclick="download(\\\''+array[i]['id']+'\\\',\\\''+array[i]['name']+'\\\')">download</button></td>'
                    html+='</tr>'
                }
                $('#file_list').html(html)
                return
            }
            if('error' in data){
                alert('刷新失败')
                return
            }
            alert("未知响应：" + JSON.stringify(data))
        }
    })
}
function child(child_folder_id) {
    save_folder_path=$('#download_file_path').val()
    html=''
    html+='<tr>'
    html+='<td>name</td>'
    html+='<td>id</td>'
    html+='<td>mimeType</td>'
    html+='<td>webViewLink</td>'
    html+='<td>download</td>'
    html+='</tr>'
    $('#file_list').html(html)
    $.ajax({
        url: '',
        type: 'post',
        data: '{"method": "goto_child_folder","params": ["'+child_folder_id+'"],"jsonrpc": "2.0","id": 6}',
        contentType: "application/x-www-form-urlencoded",
        dataType: "json",

        error: function () {
            alert("child网络错误!");
        },
        success: function (data) {
            if('result' in data){
                array = JSON.parse(JSON.stringify(data['result']))
                for (var i in array) {
                    html+='<tr>'
                    if(array[i]['mimeType']=='application/vnd.google-apps.folder'){
                        html+='<td class="name" onclick="child(\\\''+array[i]['id']+'\\\')">'+array[i]['name']+'</td>'
                    }else{
                        html+='<td>'+array[i]['name']+'</td>'
                    }
                    html+='<td>'+array[i]['id']+'</td>'
                    html+='<td>'+array[i]['mimeType']+'</td>'
                    html+='<td><a target= "_blank" href="'+array[i]['webViewLink']+'">浏览链接</a></td>'
                    html+='<td><button onclick="download(\\\''+array[i]['id']+'\\\',\\\''+array[i]['name']+'\\\')">download</button></td>'
                    html+='</tr>'
                }
                $('#file_list').html(html)
                return
            }
            if('error' in data){
                alert('刷新失败')
                return
            }
            alert("未知响应：" + JSON.stringify(data))
        }
    })
}
function wait() {
    html=''
    html+='<tr>'
    html+='<td>upload/download</td>'
    html+='<td>path</td>'
    html+='<td>id</td>'
    html+='<td>progress</td>'
    html+='<td>done</td>'
    html+='<td>file_name</td>'
    html+='<td>delete</td>'
    html+='</tr>'
    $('#wait_list').html(html)
    $.ajax({
        url: '',
        type: 'post',
        data: '{"method": "get_json_wait_works","jsonrpc": "2.0","id": 7}',
        contentType: "application/x-www-form-urlencoded",
        dataType: "json",

        error: function () {
            $('#wait_list').html(html+'<tr><td>网络错误!</td></tr>')
        },
        success: function (data) {
            if('result' in data){
                array = JSON.parse(data['result'])
                for (var i in array) {
                    html+='<tr>'
                    if(array[i]['is_download']){
                        html+='<td>download</td>'
                    }else{
                        html+='<td>upload</td>'
                    }
                    html+='<td>'+array[i]['path']+'</td>'
                    html+='<td>'+array[i]['id']+'</td>'
                    html+='<td>'+array[i]['progress']+'%</td>'
                    html+='<td>'+array[i]['done']+'</td>'
                    html+='<td>'+array[i]['file_name']+'</td>'
                    html+='<td><button onclick="delete_wait(\\\''+array[i]['is_download']+'\\\',\\\''+array[i]['path']+'\\\',\\\''+array[i]['id']+'\\\')">delete</button></td>'
                    html+='</tr>'
                }
                $('#wait_list').html(html)
                return
            }
            if('error' in data){
                $('#wait_list').html(html+'<tr><td>刷新失败</td><td>'+JSON.stringify(data)+'</td></tr>')
                return
            }
            $('#wait_list').html(html+'<tr><td>未知响应</td><td>'+JSON.stringify(data)+'</td></tr>')
        }
    })
}
function doing() {
    html=''
    html+='<tr>'
    html+='<td>upload/download</td>'
    html+='<td>path</td>'
    html+='<td>id</td>'
    html+='<td>progress</td>'
    html+='<td>done</td>'
    html+='<td>file_name</td>'
    html+='</tr>'
    $('#doing_list').html(html)
    $.ajax({
        url: '',
        type: 'post',
        data: '{"method": "get_json_doing_works","jsonrpc": "2.0","id": 8}',
        contentType: "application/x-www-form-urlencoded",
        dataType: "json",

        error: function () {
            $('#doing_list').html(html+'<tr><td>网络错误!</td></tr>')
        },
        success: function (data) {
            if('result' in data){
                array = JSON.parse(data['result'])
                for (var i in array) {
                    html+='<tr>'
                    if(array[i]['is_download']){
                        html+='<td>download</td>'
                    }else{
                        html+='<td>upload</td>'
                    }
                    html+='<td>'+array[i]['path']+'</td>'
                    html+='<td>'+array[i]['id']+'</td>'
                    html+='<td>'+array[i]['progress']+'%</td>'
                    html+='<td>'+array[i]['done']+'</td>'
                    html+='<td>'+array[i]['file_name']+'</td>'
                    html+='</tr>'
                }
                $('#doing_list').html(html)
                return
            }
            if('error' in data){
                $('#doing_list').html(html+'<tr><td>刷新失败</td><td>'+JSON.stringify(data)+'</td></tr>')
                return
            }
            $('#doing_list').html(html+'<tr><td>未知响应</td><td>'+JSON.stringify(data)+'</td></tr>')
        }
    })
}
function done() {
    html=''
    html+='<tr>'
    html+='<td>upload/download</td>'
    html+='<td>path</td>'
    html+='<td>id</td>'
    html+='<td>progress</td>'
    html+='<td>done</td>'
    html+='<td>file_name</td>'
    html+='<td>delete</td>'
    html+='</tr>'
    $('#done_list').html(html)
    $.ajax({
        url: '',
        type: 'post',
        data: '{"method": "get_json_done_works","jsonrpc": "2.0","id": 8}',
        contentType: "application/x-www-form-urlencoded",
        dataType: "json",

        error: function () {
            $('#done_list').html(html+'<tr><td>网络错误!</td></tr>')
        },
        success: function (data) {
            if('result' in data){
                array = JSON.parse(data['result'])
                for (var i in array) {
                    html+='<tr>'
                    if(array[i]['is_download']){
                        html+='<td>download</td>'
                    }else{
                        html+='<td>upload</td>'
                    }
                    html+='<td>'+array[i]['path']+'</td>'
                    html+='<td>'+array[i]['id']+'</td>'
                    html+='<td>'+array[i]['progress']+'%</td>'
                    html+='<td>'+array[i]['done']+'</td>'
                    html+='<td>'+array[i]['file_name']+'</td>'
                    html+='<td><button onclick="delete_done(\\\''+array[i]['is_download']+'\\\',\\\''+array[i]['path']+'\\\',\\\''+array[i]['id']+'\\\')">delete</button></td>'
                    html+='</tr>'
                }
                $('#done_list').html(html)
                return
            }
            if('error' in data){
                $('#done_list').html(html+'<tr><td>刷新失败</td><td>'+JSON.stringify(data)+'</td></tr>')
                return
            }
            $('#done_list').html(html+'<tr><td>未知响应</td><td>'+JSON.stringify(data)+'</td></tr>')
        }
    })
}
</script>


    <script type="text/javascript">
        flush();
        setInterval('wait()', 7890);
        setInterval('doing()', 3456);
        setInterval('done()', 5678);
    </script>

</html>
"""
