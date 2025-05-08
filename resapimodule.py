import openai
import os
import json

# OpenAI APIキーを安全に取得する関数
def get_secret():
    """APIキーを取得する関数"""
    api_key = os.getenv('OPENAI_API_KEY')
    
    if not api_key:
        try:
            with open('/run/secrets/openai_api_key', 'r') as f:
                api_key = f.read().strip()
        except (FileNotFoundError, IOError):
            pass
    
    if not api_key:
        raise Exception("APIキーが設定されていません")
        
    return api_key

# OpenAI APIキーを設定
openai.api_key = get_secret()
openai.timeout = 300  # タイムアウトを300秒に設定

# 会話のidを保存
lcl_previous_response_id = ""


def get_rag_list():
    # RAGリストを取得するためのAPI呼び出しを実装
    output_lines = []
    try:
        response = openai.vector_stores.list()
        print(response)
        for vs in response.data:
            print(f"FileName: {vs.name}, ID: {vs.id}, Bytes: {vs.usage_bytes}")
            # file_info = {'FileName': {vs.name}, 'ID': { vs.id}, 'Bytes': {vs.usage_bytes}}
            file_info = {'FileName': vs.name,
                         'ID': vs.id, 'Bytes': vs.usage_bytes}
            output_lines.append(file_info)
    except openai.APIError as e:
        print(f"OpenAI APIエラー: {e}")
        output_string = f"APIエラーが発生しました<br>\n{e}"
    except (ValueError, TypeError, KeyError) as e:  # Replace with specific exceptions
        print(f"予期せぬエラー: {e}")
        output_string = f"APIエラーが発生しました<br>\n{e}"
    return output_lines


def get_rag_search(usequery: str, ragid: str, my_previous_response_id: str = None) -> str:
    output_string = ""
    previous_response_id = ""
    try:
        # response = None
        response = openai.responses.create(
            model="gpt-4.1",
            input=usequery,
            tools=[
                {"type": "file_search",
                 "vector_store_ids": [f"{ragid}"],
                 "max_num_results": 3
                 }],
            **({"previous_response_id": lcl_previous_response_id} if lcl_previous_response_id else {})
        )
        # Extract annotations from the response
        annotations = None
        if len(response.output) > 1:
            annotations = response.output[1].content[0].annotations
        # Get top-k retrieved filenames
        retrieved_files = set(
            [result.filename for result in annotations]) if annotations else None

        print(f'Files used: {retrieved_files}')
        print(response.output_text)
        output_string = response.output_text

        # retrieved_filesが存在する場合、output_stringに追記
        if retrieved_files:
            output_string += f"\n***\n次の資料から回答を作成しました: {', '.join(retrieved_files)}"

        # 会話履歴を更新
        previous_response_id = response.id
    except openai.APIError as e:
        print(f"OpenAI APIエラー: {e}")
        output_string = f"APIエラーが発生しました<br>\n{e}"
    except Exception as e:
        print(f"予期せぬエラー: {e}")
        output_string = f"APIエラーが発生しました<br>\n{e}"

    return output_string, previous_response_id


def get_search(usequery: str) -> str:
    output_string = ""
    try:
        response = openai.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "user", "content": f"{usequery}"},
            ]
        )

        print("Response全体:", json.dumps(response, indent=4, ensure_ascii=False))
        # print(response.choices[0].message.content)
        output_string = response.choices[0].message.content

    except openai.APIError as e:
        print(f"OpenAI APIエラー: {e}")
        output_string = f"APIエラーが発生しました<br>\n{e}"
    except Exception as e:
        print(f"予期せぬエラー: {e}")
        output_string = f"APIエラーが発生しました<br>\n{e}"

    return output_string


def get_search_byresponse(usequery: str, IsNewChat: bool = True) -> str:
    output_string = ""
    try:
        global lcl_previous_response_id
        if IsNewChat == True:
            lcl_previous_response_id = ""
        response = openai.responses.create(
            model="gpt-4.1",
            tools=[{"type": "web_search_preview"}],
            tool_choice="required",
            input=usequery,
            **({"previous_response_id": lcl_previous_response_id} if lcl_previous_response_id else {})
        )

        print("n\n\n----------\n" + response.output_text)
        output_string = response.output_text
        lcl_previous_response_id = response.id
        value1 = response.text.format

    except openai.APIError as e:
        print(f"OpenAI APIエラー: {e}")
        output_string = f"APIエラーが発生しました<br>\n{e}"
    except Exception as e:
        print(f"予期せぬエラー: {e}")
        output_string = f"APIエラーが発生しました<br>\n{e}"

    return output_string


def get_pdf_search(usequery: str, filename: str, contexttype: str, filebase64: str, IsNewChat: bool = True) -> str:
    # https://platform.openai.com/docs/guides/images-vision?api-mode=responses&format=base64-encoded
    # https://platform.openai.com/docs/guides/pdf-files?api-mode=responses 参照のこと
    # https://platform.openai.com/docs/assistants/tools/file-search#supported-files
    output_string = ""
    try:
        tgttype = "input_file"
        # file_ext = os.path.splitext(filename)[1][1:]
        global lcl_previous_response_id
        if IsNewChat == True:
            lcl_previous_response_id = ""

        # 既存の会話を続ける場合、previous_response_idを使用
        response = openai.responses.create(
            model="gpt-4.1",
            tools=[{"type": "web_search_preview"}],
            tool_choice="required",
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": f"{tgttype}",
                            "filename": f"{filename}",
                            "file_data": f"data:{contexttype};base64,{filebase64}",
                        },
                        {
                            "type": "input_text",
                            "text": f"{usequery}",
                        },
                    ],
                }],
            **({"previous_response_id": lcl_previous_response_id} if lcl_previous_response_id else {})
        )

        print("n\n\n----------\n" + response.output_text)
        output_string = response.output_text
        lcl_previous_response_id = response.id
        value1 = response.text.format

    except openai.APIError as e:
        print(f"OpenAI APIエラー: {e}")
        output_string = f"APIエラーが発生しました<br>\n{e}"
    except Exception as e:
        print(f"予期せぬエラー: {e}")
        output_string = f"APIエラーが発生しました<br>\n{e}"

    return output_string


def get_image_search(usequery: str, filename: str, contexttype: str, filebase64: str, IsNewChat: bool = True) -> str:
    # https://platform.openai.com/docs/guides/images-vision?api-mode=responses&format=base64-encoded
    # https://platform.openai.com/docs/guides/pdf-files?api-mode=responses 参照のこと
    output_string = ""
    try:
        # tgttype = "input_file"
        tgttype = "input_image"
        global lcl_previous_response_id
        if IsNewChat == True:
            lcl_previous_response_id = ""
        # 既存の会話を続ける場合、previous_response_idを使用
        response = openai.responses.create(
            model="gpt-4.1",
            tools=[{"type": "web_search_preview"}],
            tool_choice="auto",
            input=[
                {
                        "role": "user",
                        "content": [
                            {
                                "type": f"{tgttype}",
                                "image_url": f"data:{contexttype};base64,{filebase64}",
                            },
                            {
                                "type": "input_text",
                                "text": f"{usequery}",
                            },
                        ],
                }],
            **({"previous_response_id": lcl_previous_response_id} if lcl_previous_response_id else {})
        )

        print("n\n\n----------\n" + response.output_text)
        output_string = response.output_text
        lcl_previous_response_id = response.id
        value1 = response.text.format

    except openai.APIError as e:
        print(f"OpenAI APIエラー: {e}")
        output_string = f"APIエラーが発生しました<br>\n{e}"
    except Exception as e:
        print(f"予期せぬエラー: {e}")
        output_string = f"APIエラーが発生しました<br>\n{e}"

    return output_string
