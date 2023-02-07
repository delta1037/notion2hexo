# author: delta1037
# Date: 2023/02/07
# mail:geniusrabbit@qq.com
# 打包代码 pyinstaller -F -c notion2hexo.py -p configuration_service.py
import json
import os
import shutil
import time

import oss2
import NotionDump
from NotionDump.Dump.database import Database
from NotionDump.Dump.dump import Dump
from NotionDump.Notion.Notion import NotionQuery
from configuration_service import ConfigurationService

# 内容下载配置
NotionDump.FORMAT_DATE = "%Y-%m-%d"
NotionDump.FORMAT_DATETIME = "%Y-%m-%d %H:%M:%S"
NotionDump.S_PAGE_PROPERTIES = False
NotionDump.MD_DIVIDER = "<!-- more -->"
# 图片缓存位置
IMAGE_BUFFER_DB = "./image_db.json"


class Notion2Hexo:
    def __init__(self):
        # 配置
        self.__config = ConfigurationService()
        # 查询handle
        self.__query_handle = NotionQuery(token=self.__config.get_key("notion_key"))
        # 图片链接缓存
        if os.path.exists(IMAGE_BUFFER_DB):
            image_fd = open(IMAGE_BUFFER_DB, 'r')
            self.image_db = json.load(image_fd)
        else:
            self.image_db = {}

        # oss 权限
        auth = oss2.Auth(self.__config.get_key("oss_access_key_id"), self.__config.get_key("oss_access_key_secret"))
        self.image_bucket = oss2.Bucket(auth, "https://" + self.__config.get_key("oss_endpoint"), self.__config.get_key("bucket_name"))

        # 生成过程中的错误
        self.error_list = []

        if os.path.exists(self.__config.get_key("local_dir")):
            shutil.rmtree(self.__config.get_key("local_dir"))
        os.mkdir(self.__config.get_key("local_dir"))

    def dump_data(self):
        blog_struct = Dump(
            dump_id=self.__config.get_key("blog_db_id"),
            query_handle=self.__query_handle,
            export_child_pages=True,
            dump_type=NotionDump.DUMP_TYPE_DB_TABLE,
            db_parser_type=NotionDump.PARSER_TYPE_MD,
            page_parser_type=NotionDump.PARSER_TYPE_MD
        ).dump_to_file()
        blog_dict = Database(
            database_id=self.__config.get_key("blog_db_id"),
            query_handle=self.__query_handle
        ).dump_to_dic()
        # print(blog_struct)
        # print(blog_dict)

        # 遍历博客字典，处理每一个blog
        for blog in blog_dict:
            print("[proc blog]", blog["_page_id"])
            if blog["发布"] == NotionDump.MD_BOOL_FALSE:
                print("[proc blog] skip")
                continue
            print(blog)
            if blog["_page_id"] not in blog_struct:
                continue
            blog_info = blog_struct[blog["_page_id"]]
            print(blog_info)
            if not blog_info["dumped"]:
                self.error_list.append("[proc blog] blog " + blog["标题"] + " dumped fail")

            # 生成文件头信息
            head_info = "---\n"
            head_info += "title: " + blog["标题"] + "\n"
            head_info += "tags:\n"
            for tag in blog["标签"].split(','):
                head_info += "  - " + tag + "\n"
            head_info += "categories:\n  - " + blog["类别"] + "\n"
            head_info += "date: " + blog["日期"] + "\n"
            head_info += "top: " + str(blog["置顶"] == NotionDump.MD_BOOL_TRUE) + "\n"
            head_info += "---\n"
            # print(head_info)

            # 获取文章体内容进行拼接
            if blog_info["local_path"] == "" or not os.path.exists(blog_info["local_path"]):
                self.error_list.append("[proc blog] blog " + blog["标题"] + " not exist")
                continue
            file_content = open(blog_info["local_path"], 'r', encoding='utf-8').read()
            blog_local_path = self.__config.get_key("local_dir") + "/" + self.__get_safe_file_name(blog["本地目录"]) + "/"
            if not os.path.exists(blog_local_path):
                os.mkdir(blog_local_path)

            filename = blog_local_path + self.__get_safe_file_name(blog["标题"]) + ".md"
            hexo_blog_file = open(filename, "w", encoding="utf-8")
            hexo_blog_file.write(head_info + file_content)
            hexo_blog_file.close()

            link_idx = 0
            for link_id in blog_info['child_pages']:
                block_info = blog_struct[link_id]
                # print(image_info)
                link_url = self.__proc_link(
                    link_idx,
                    link_id,
                    block_info,
                    blog["本地目录"],
                    self.__get_safe_file_name(blog["标题"])
                )
                link_idx += 1
                if block_info['page_name'] != "":
                    link_des = "![" + block_info['page_name'] + "](" + link_url + ")"
                else:
                    link_des = "![image](" + link_url + ")"
                link_src = "[" + link_id + "]()"
                self.__relocate_link(filename, link_src, link_des)

        # 保存缓存内容
        json_str = json.dumps(self.image_db, indent=4)
        with open(IMAGE_BUFFER_DB, 'w') as json_file:
            json_file.write(json_str)

    # 处理md文件中链接到的图片
    def __proc_link(self, link_idx, link_id, block_info, local_dir, blog_name):
        if link_id is None or block_info is None:
            self.error_list.append("[proc link] !!! block info is invalid !!!")
            return ""
        # print(block_info)

        # 将图片上传到aliyun OSS 并获取到图片链接
        if block_info["type"] == "image":
            # 生成上传文件名
            image_suffix = block_info["local_path"][block_info["local_path"].rfind("."):]
            if block_info['page_name'] != "":
                image_upload_url = self.__get_safe_file_name(local_dir + "_" + blog_name + "_" + block_info['page_name']) + image_suffix
            else:
                image_upload_url = self.__get_safe_file_name(local_dir + "_" + blog_name + "_" + "image-idx-" + str(link_idx)) + image_suffix
            print("upload_url:", image_upload_url)
            print("local_path:", block_info["local_path"])
            if image_upload_url == "" or block_info["local_path"] == "":
                self.error_list.append("[proc link] !!! block info error !!!")
                return ""
            # 新增缓存处理
            if link_id in self.image_db and self.image_db[link_id]["upload_url"] == image_upload_url:
                if "create_time" not in self.image_db[link_id]:
                    self.image_db[link_id]["create_time"] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                self.image_db[link_id]["access_time"] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                return self.image_db[link_id]["oss_link"]

            print("[proc link] upload file", block_info["local_path"])
            ret_status = self.image_bucket.put_object_from_file(
                self.__config.get_key("upload_prefix") + image_upload_url,
                block_info["local_path"]
            )
            if ret_status.status != 200:
                self.error_list.append("[proc link] !!! image upload fail, status=" + str(ret_status.status) + " !!!")

            self.image_db[link_id] = {
                "oss_link":
                    "https://" + self.__config.get_key("bucket_name") + "." + self.__config.get_key("oss_endpoint") + "/" +
                    self.__config.get_key("upload_prefix") + image_upload_url,
                "upload_url": image_upload_url,
                "local_path": block_info["local_path"],
                "create_time": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()),
                "access_time": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            }
            return self.image_db[link_id]["oss_link"]
        else:
            self.error_list.append("[proc link] !!! block type" + block_info["type"] + " is invalid !!!")
            return ""

    @staticmethod
    def __get_safe_file_name(file_name):
        # 文件名不能包含的特殊字符： \ / : * ? " < > |
        file_name = file_name.replace("\\", "-")
        file_name = file_name.replace("/", "-")
        file_name = file_name.replace(":", "-")
        file_name = file_name.replace("*", "-")
        file_name = file_name.replace("?", "-")
        file_name = file_name.replace("|", "-")
        file_name = file_name.replace("\"", "-")
        file_name = file_name.replace("”", "-")
        file_name = file_name.replace("<", "-")
        file_name = file_name.replace(">", "-")
        # 去掉公式特性
        file_name = file_name.replace("$", "-")
        # 去掉换行
        file_name = file_name.replace("\n", "-")
        # 去掉空格
        file_name = file_name.replace(" ", "")
        return file_name

    # 文件中的字符串替换
    @staticmethod
    def __relocate_link(file_name, src_str, des_str):
        file = open(file_name, 'r', encoding='utf-8')
        all_lines = file.readlines()
        file.close()

        file = open(file_name, 'w+', encoding='utf-8')
        for line in all_lines:
            line = line.replace(src_str, des_str)
            file.writelines(line)
        file.close()


if __name__ == '__main__':
    blog_handle = Notion2Hexo()
    blog_handle.dump_data()
    print("errors:")
    print(blog_handle.error_list)
