import json
import os
import shutil

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
# 图片缓存位置
IMAGE_BUFFER_DB = "./image_db.json"


class Notion2Hexo:
    def __init__(self):
        # 配置
        self.__config = ConfigurationService()
        # 查询handle
        self.__query_handle = NotionQuery(token=self.__config.get_key("notion_key"))
        # 图片链接缓存
        image_fd = open(IMAGE_BUFFER_DB, 'r')
        if image_fd is not None:
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
            head_info += "---\n"
            print(head_info)

            # 获取文章体内容进行拼接
            file_content = open(blog_info["local_path"], 'r', encoding='utf-8').read()
            blog_local_path = self.__config.get_key("local_dir") + "/" + blog["本地目录"] + "/"
            if not os.path.exists(blog_local_path):
                os.mkdir(blog_local_path)

            filename = blog_local_path + self.__get_safe_file_name(blog["标题"]) + ".md"
            hexo_blog_file = open(filename, "w", encoding="utf-8")
            hexo_blog_file.write(head_info + file_content)
            hexo_blog_file.close()

            image_idx = 0
            for image_id in blog_info['child_pages']:
                image_info = blog_struct[image_id]
                # print(image_info)
                image_url = self.__proc_image(
                    image_idx,
                    image_id,
                    image_info,
                    blog["本地目录"],
                    self.__get_safe_file_name(blog["标题"])
                )
                image_idx += 1
                if image_info['page_name'] != "":
                    image_des = "![" + image_info['page_name'] + "](" + image_url + ")"
                else:
                    image_des = "![image](" + image_url + ")"
                image_src = "[" + image_id + "]()"
                self.__relocate_link(filename, image_src, image_des)

        json_str = json.dumps(self.image_db, indent=4)
        with open(IMAGE_BUFFER_DB, 'w') as json_file:
            json_file.write(json_str)

    # 处理md文件中链接到的图片
    def __proc_image(self, image_idx, image_id, image_info, loca_dir, blog_name):
        if image_id is None or image_info is None:
            self.error_list.append("!!! IMAGE info is invalid !!!")
            return "!!! IMAGE info is invalid !!!"
        # 将图片上传到aliyun OSS 并获取到图片链接
        print(image_info)

        # 生成上传文件名
        image_suffix = image_info["local_path"][image_info["local_path"].rfind("."):]
        if image_info['page_name'] != "":
            image_upload_url = self.__get_safe_file_name(loca_dir + "_" + blog_name + "_" + image_info['page_name']) + image_suffix
        else:
            image_upload_url = self.__get_safe_file_name(loca_dir + "_" + blog_name + "_" + "image-idx-" + str(image_idx)) + image_suffix
        print("upload_url:", image_upload_url)
        print("local_path:", image_info["local_path"])
        # 新增缓存处理
        if image_id in self.image_db and self.image_db[image_id]["upload_url"] == image_upload_url:
            return self.image_db[image_id]["oss_link"]

        self.image_bucket.put_object_from_file(
            self.__config.get_key("upload_prefix") + image_upload_url,
            image_info["local_path"]
        )

        self.image_db[image_id] = {
            "oss_link":
                "https://" + self.__config.get_key("bucket_name") + "." + self.__config.get_key("oss_endpoint") + "/" +
                self.__config.get_key("upload_prefix") + image_upload_url,
            "upload_url": image_upload_url,
            "local_path": image_info["local_path"],
        }
        return self.image_db[image_id]["oss_link"]

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
