Qwen-Omni 模型能够接收文本与单一其他模态（图片、音频、视频）的组合输入，并生成文本或语音形式的回复， 提供多种拟人音色，支持多语言和方言的语音输出，可应用于文本创作、视觉识别、语音助手等场景。

## **快速开始**

**前提条件**

-   已[配置 API Key](https://help.aliyun.com/zh/model-studio/get-api-key)并[配置API Key到环境变量](https://help.aliyun.com/zh/model-studio/configure-api-key-through-environment-variables)。
    
-   Qwen-Omni 模型仅支持 OpenAI 兼容方式调用，需要[安装最新版SDK](https://help.aliyun.com/zh/model-studio/install-sdk)。OpenAI Python SDK 最低版本为 1.52.0， Node.js SDK 最低版本为 4.68.0。
    

**调用方式**：Qwen-Omni 目前仅支持以流式输出的方式进行调用，`stream`参数必须设置为`True`，否则会报错。

以下示例将一段文本发送至 Qwen-Omni的API接口，并流式返回文本和音频的回复。

Python

```
# 运行前的准备工作:
# 运行下列命令安装第三方依赖
# pip install numpy soundfile openai

import os
import base64
import soundfile as sf
import numpy as np
from openai import OpenAI

# 1. 初始化客户端
client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),  # 确认已配置环境变量
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

# 2. 发起请求
try:
    completion = client.chat.completions.create(
        model="qwen3-omni-flash",
        messages=[{"role": "user", "content": "你是谁"}],
        modalities=["text", "audio"],  # 指定输出文本和音频
        audio={"voice": "Cherry", "format": "wav"},
        stream=True,  # 必须设置为 True
        stream_options={"include_usage": True},
    )

    # 3. 处理流式响应并解码音频
    print("模型回复：")
    audio_base64_string = ""
    for chunk in completion:
        # 处理文本部分
        if chunk.choices and chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="")

        # 收集音频部分
        if chunk.choices and hasattr(chunk.choices[0].delta, "audio") and chunk.choices[0].delta.audio:
            audio_base64_string += chunk.choices[0].delta.audio.get("data", "")

    # 4. 保存音频文件
    if audio_base64_string:
        wav_bytes = base64.b64decode(audio_base64_string)
        audio_np = np.frombuffer(wav_bytes, dtype=np.int16)
        sf.write("audio_assistant.wav", audio_np, samplerate=24000)
        print("\n音频文件已保存至：audio_assistant.wav")

except Exception as e:
    print(f"请求失败: {e}")
```

Node.js

```
// 运行前的准备工作:
// Windows/Mac/Linux 通用:
// 1. 确保已安装 Node.js (建议版本 >= 14)
// 2. 运行以下命令安装必要的依赖:
//    npm install openai wav

import OpenAI from "openai";
import { createWriteStream } from 'node:fs';
import { Writer } from 'wav';

// 定义音频转换函数：将Base64字符串转换并保存为标准的 WAV 音频文件
async function convertAudio(audioString, audioPath) {
    try {
        // 解码Base64字符串为Buffer
        const wavBuffer = Buffer.from(audioString, 'base64');
        // 创建WAV文件写入流
        const writer = new Writer({
            sampleRate: 24000,  // 采样率
            channels: 1,        // 单声道
            bitDepth: 16        // 16位深度
        });
        // 创建输出文件流并建立管道连接
        const outputStream = createWriteStream(audioPath);
        writer.pipe(outputStream);

        // 写入PCM数据并结束写入
        writer.write(wavBuffer);
        writer.end();

        // 使用Promise等待文件写入完成
        await new Promise((resolve, reject) => {
            outputStream.on('finish', resolve);
            outputStream.on('error', reject);
        });

        // 添加额外等待时间确保音频完整
        await new Promise(resolve => setTimeout(resolve, 800));

        console.log(`\n音频文件已成功保存为 ${audioPath}`);
    } catch (error) {
        console.error('处理过程中发生错误:', error);
    }
}

//  1. 初始化客户端
const openai = new OpenAI(
    {
        // 若没有配置环境变量，请用阿里云百炼API Key将下行替换为：apiKey: "sk-xxx",
        apiKey: process.env.DASHSCOPE_API_KEY,
        baseURL: "https://dashscope.aliyuncs.com/compatible-mode/v1"
    }
);
// 2. 发起请求
const completion = await openai.chat.completions.create({
    model: "qwen3-omni-flash",  
    messages: [
        {
            "role": "user",
            "content": "你是谁？"
        }],
    stream: true,
    stream_options: {
        include_usage: true
    },
    modalities: ["text", "audio"],
    audio: { voice: "Cherry", format: "wav" }
});

let audioString = "";
console.log("大模型的回复：")

// 3. 处理流式响应并解码音频
for await (const chunk of completion) {
    if (Array.isArray(chunk.choices) && chunk.choices.length > 0) {
        // 处理文本内容
        if (chunk.choices[0].delta.content) {
            process.stdout.write(chunk.choices[0].delta.content);
        }
        // 处理音频内容
        if (chunk.choices[0].delta.audio) {
            if (chunk.choices[0].delta.audio["data"]) {
                audioString += chunk.choices[0].delta.audio["data"];
            }
        }
    }
}
// 4. 保存音频文件
convertAudio(audioString, "audio_assistant.wav");
```

curl

```
curl -X POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions \
-H "Authorization: Bearer $DASHSCOPE_API_KEY" \
-H "Content-Type: application/json" \
-d '{
    "model": "qwen3-omni-flash",
    "messages": [
        {
            "role": "user", 
            "content": "你是谁？"
        }
    ],
    "stream":true,
    "stream_options":{
        "include_usage":true
    },
    "modalities":["text","audio"],
    "audio":{"voice":"Cherry","format":"wav"}
}'
```

**返回结果**

运行`Python`和`Node.js`代码后，将在控制台看到模型的文本回复，并在代码文件目录下找到一个名为`audio_assistant.wav` 的音频文件。

```
大模型的回复：
我是阿里云研发的大规模语言模型，我叫千问。有什么我可以帮助你的吗？
```

运行`HTTP`代码将直接返回文本和`Base64`编码（`audio`字段）的音频数据。

```
data: {"choices":[{"delta":{"content":"我"},"finish_reason":null,"index":0,"logprobs":null}],"object":"chat.completion.chunk","usage":null,"created":1757647879,"system_fingerprint":null,"model":"qwen3-omni-flash","id":"chatcmpl-a68eca3b-c67e-4666-a72f-73c0b4919860"}
data: {"choices":[{"delta":{"content":"是"},"finish_reason":null,"index":0,"logprobs":null}],"object":"chat.completion.chunk","usage":null,"created":1757647879,"system_fingerprint":null,"model":"qwen3-omni-flash","id":"chatcmpl-a68eca3b-c67e-4666-a72f-73c0b4919860"}
......
data: {"choices":[{"delta":{"audio":{"data":"/v8AAAAAAAAAAAAAAA...","expires_at":1757647879,"id":"audio_a68eca3b-c67e-4666-a72f-73c0b4919860"}},"finish_reason":null,"index":0,"logprobs":null}],"object":"chat.completion.chunk","usage":null,"created":1757647879,"system_fingerprint":null,"model":"qwen3-omni-flash","id":"chatcmpl-a68eca3b-c67e-4666-a72f-73c0b4919860"}
data: {"choices":[{"finish_reason":"stop","delta":{"content":""},"index":0,"logprobs":null}],"object":"chat.completion.chunk","usage":null,"created":1764763585,"system_fingerprint":null,"model":"qwen3-omni-flash","id":"chatcmpl-e8c82e9e-073e-4289-a786-a20eb444ac9c"}
data: {"choices":[],"object":"chat.completion.chunk","usage":{"prompt_tokens":207,"completion_tokens":103,"total_tokens":310,"completion_tokens_details":{"audio_tokens":83,"text_tokens":20},"prompt_tokens_details":{"text_tokens":207}},"created":1757940330,"system_fingerprint":null,"model":"qwen3-omni-flash","id":"chatcmpl-9cdd5a26-f9e9-4eff-9dcc-93a878165afc"}
```

## **适用范围**

### **支持的地域**

-   北京：需使用该地域的[API Key](https://bailian.console.aliyun.com/?tab=model#/api-key)
    
-   新加坡：需使用该地域的[API Key](https://bailian.console.aliyun.com/?tab=model#/api-key)
    

### **支持的模型**

相比于 [Qwen-VL](https://help.aliyun.com/zh/model-studio/vision) 与 [Qwen-Audio](https://help.aliyun.com/zh/model-studio/audio-language-model) 模型，Qwen-Omni 模型可以：

-   理解视频文件中的视觉与音频信息；
    
-   理解多种模态的数据；
    
-   输出音频；
    

在视觉理解、音频理解等能力上也表现出色。

建议优先使用Qwen3-Omni-Flash**，**相较于Qwen-Omni-Turbo（后续不再更新），模型的能力得到大幅提升：

-   **支持思考模式和非思考模式，**可通过 `enable_thinking` 参数实现两种模式的切换，默认不开启思考模式。
    
-   在非思考模式下，对于模型输出的音频：
    
    -   qwen3-omni-flash-2025-12-01支持的音色增加至49种，qwen3-omni-flash-2025-09-15、qwen3-omni-flash支持的音色种类增加至 17 种，Qwen-Omni-Turbo 仅支持 4 种；
        
    -   支持语言种类增加至 10 种，Qwen-Omni-Turbo 仅支持 2 种。
        

## 中国内地（北京）

## 商业版模型

相较于开源版，商业版模型具有最新的能力和改进。

| **模型名称** | **版本** | **模式** | **上下文长度** | **最大输入** | **最长思维链** | **最大输出** | **免费额度** [（注）](https://help.aliyun.com/zh/model-studio/new-free-quota#591f3dfedfyzj) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **（Token数）** |   |   |   |
| **qwen3-omni-flash** > 当前与qwen3-omni-flash-2025-12-01能力相同 | 稳定版 | 思考模式 | 65,536 | 16,384 | 32,768 | 16,384 | 各100万Token（不区分模态） 有效期：百炼开通后90天内 |
| 非思考模式 | 49,152 | \\- |
| qwen3-omni-flash-2025-12-01 | 快照版 | 思考模式 | 65,536 | 16,384 | 32,768 | 16,384 |
| 非思考模式 | 49,152 | \\- |
| qwen3-omni-flash-2025-09-15 > 又称qwen3-omni-flash-0915 | 思考模式 | 65,536 | 16,384 | 32,768 | 16,384 |
| 非思考模式 | 49,152 | \\- |

**更多模型**

| **模型名称** | **版本** | **上下文长度** | **最大输入** | **最大输出** | **免费额度** [（注）](https://help.aliyun.com/zh/model-studio/new-free-quota#591f3dfedfyzj) |
| --- | --- | --- | --- | --- | --- |
| **（Token数）** |   |   |
| **qwen-omni-turbo** > 当前与qwen-omni-turbo-2025-03-26能力相同 > [Batch调用](https://help.aliyun.com/zh/model-studio/batch-interfaces-compatible-with-openai/)半价 | 稳定版 | 32,768 | 30,720 | 2,048 | 各100万Token（不区分模态） 有效期：百炼开通后90天内 |
| **qwen-omni-turbo-latest** > 始终与最新快照版 能力相同 | 最新版 |
| qwen-omni-turbo-2025-03-26 > 又称qwen-omni-turbo-0326 | 快照版 |
| qwen-omni-turbo-2025-01-19 > 又称qwen-omni-turbo-0119 |

## 开源版模型

| **模型名称** | **上下文长度** | **最大输入** | **最大输出** | **免费额度** [（注）](https://help.aliyun.com/zh/model-studio/new-free-quota#591f3dfedfyzj) |
| --- | --- | --- | --- | --- |
| **（Token数）** |   |   |
| qwen2.5-omni-7b | 32,768 | 30,720 | 2,048 | 100万Token（不区分模态） 有效期：百炼开通后90天 |

## 国际（新加坡）

## 商业版模型

| **模型名称** | **版本** | **模式** | **上下文长度** | **最大输入** | **最长思维链** | **最大输出** | **免费额度** [（注）](https://help.aliyun.com/zh/model-studio/new-free-quota#591f3dfedfyzj) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **（Token数）** |   |   |   |
| **qwen3-omni-flash** > 当前与qwen3-omni-flash-2025-12-01能力相同 | 稳定版 | 思考模式 | 65,536 | 16,384 | 32,768 | 16,384 | 无免费额度 |
| 非思考模式 | 49,152 | \\- |
| qwen3-omni-flash-2025-12-01 | 快照版 | 思考模式 | 65,536 | 16,384 | 32,768 | 16,384 |
| 非思考模式 | 49,152 | \\- |
| qwen3-omni-flash-2025-09-15 > 又称qwen3-omni-flash-0915 | 快照版 | 思考模式 | 65,536 | 16,384 | 32,768 | 16,384 |
| 非思考模式 | 49,152 | \\- |

**更多模型**

| **模型名称** | **版本** | **上下文长度** | **最大输入** | **最大输出** | **免费额度** [（注）](https://help.aliyun.com/zh/model-studio/new-free-quota#591f3dfedfyzj) |
| --- | --- | --- | --- | --- | --- |
| **（Token数）** |   |   |
| **qwen-omni-turbo** > 当前与qwen-omni-turbo-2025-03-26能力相同 | 稳定版 | 32,768 | 30,720 | 2,048 | 无免费额度 |
| **qwen-omni-turbo-latest** > 始终与最新快照版 > 能力相同 | 最新版 |
| qwen-omni-turbo-2025-03-26 > 又称qwen-omni-turbo-0326 | 快照版 |

## 开源版模型

| **模型名称** | **上下文长度** | **最大输入** | **最大输出** | **免费额度** [（注）](https://help.aliyun.com/zh/model-studio/new-free-quota#591f3dfedfyzj) |
| --- | --- | --- | --- | --- |
| **（Token数）** |   |   |
| qwen2.5-omni-7b | 32,768 | 30,720 | 2,048 | 无免费额度 |

## **使用方式**

**输入**

-   **支持的输入模态**：
    
    -   [文本输入](#957a002581dve)
        
    -   [图片+文本输入](#cfe42b3edcrve)
        
    -   [音频+文本输入](#b4d9c9c405qwg)
        
    -   [视频（包括图像列表与视频文件形式）+文本输入](#4a1a20f083dji)
        

> 在单条 `user` 消息中，`content` 数组可以包含文本和**一种**其他模态（图片、音频或视频），不能同时包含多种。

-   **输入多模态数据的方式：**
    
    -   公网 URL
        
    -   Base64 编码，具体用法请参见[输入 Base64 编码的本地文件](#c516d1e824x03)
        

**输出**

-   **支持的输出模态：**其中输出的音频为`Base64`编码数据，可参见[解析输出的Base64 编码的音频数据](#423736d367a7x)将其换为音频文件。
    
    | **输出模态** | `**modalities**`**参数值** | **回复风格** |
    | --- | --- | --- |
    | 文本  | \\["text"\\]（默认值） | 比较书面化，回复内容较为正式。 |
    | 文本+音频 | \\["text","audio"\\] > Qwen3-Omni-Flash在思考模式下，不支持输出音频。 | 比较口语化，回复内容包含语气词，会引导用户与其进一步交流。 > Qwen-Omni-Turbo 在输出模态包括音频时**不支持设定 System Message。** |
    
-   **支持输出的音频语言：**
    
    -   Qwen-Omni-Turbo**：**仅支持汉语（普通话）和英语。
        
    -   Qwen3-Omni-Flash（非思考模式）：支持汉语（普通话，部分方言），英语，法语、德语、俄语、意语、西语、葡语、日语、韩语。
        
-   **支持的音色：**输出音频的音色与文件格式通过`audio`参数来配置，如：`audio={"voice": "Cherry", "format": "wav"}`：
    
    -   文件格式（`format`）：只支持设定为`"wav"`；
        
    -   音频音色（`voice）`：各模型支持的音色可参见[音色列表](#61a6a8b444e6b)。
        

**限制**

-   **必须使用流式输出**：所有对 Qwen-Omni 模型的请求都必须设置 `stream=True`。
    
-   **仅 Qwen3-Omni-Flash** 模型属于混合思考模型，调用方法请参见[开启/关闭思考模式](#c02e7bf0f9ysx)，在思考模式下，**不支持输出音频。**
    

## **开启/关闭思考模式**

Qwen3-Omni-Flash 模型属于混合思考模型，通过`enable_thinking`参数控制是否开启思考模式：

-   `true`：开启思考模式
    
-   `false`（默认）：关闭思考模式
    

> `Qwen-Omni-Turbo`不属于思考模型。

## OpenAI 兼容

Python

```
import os
from openai import OpenAI

client = OpenAI(
    # 若没有配置环境变量，请用阿里云百炼API Key将下行替换为：api_key="sk-xxx",
    # 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    # 以下是北京地域base_url，如果使用新加坡地域的模型，需要将base_url替换为：https://dashscope-intl.aliyuncs.com/compatible-mode/v1
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

completion = client.chat.completions.create(
    model="qwen3-omni-flash",
    messages=[{"role": "user", "content": "你是谁"}],
    
    # 开启/关闭思考模式，在思考模式下不支持输出音频；qwen-omni-turbo不支持设置enable_thinking。   
    extra_body={'enable_thinking': True},
    
    # 设置输出数据的模态，非思考模式下当前支持两种：["text","audio"]、["text"]，思考模式仅支持：["text"]
    modalities=["text"],
    
    # 设置音色，思考模式下不支持设置audio参数
    # audio={"voice": "Cherry", "format": "wav"},
    # stream 必须设置为 True，否则会报错
    stream=True,
    stream_options={"include_usage": True},
)

for chunk in completion:
    if chunk.choices:
        print(chunk.choices[0].delta)
    else:
        print(chunk.usage)
```

Node.js

```
import OpenAI from "openai";

const openai = new OpenAI({
     // 若没有配置环境变量，请用阿里云百炼API Key将下行替换为：apiKey:"sk-xxx",
    // 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
    apiKey: process.env.DASHSCOPE_API_KEY, 
    // 以下是北京地域base_url，如果使用新加坡地域的模型，需要将base_url替换为：https://dashscope-intl.aliyuncs.com/compatible-mode/v1
    baseURL: 'https://dashscope.aliyuncs.com/compatible-mode/v1'
});

const completion = await openai.chat.completions.create({
    model: "qwen3-omni-flash",
    messages: [
        { role: "user", content: "你是谁？" }
    ],
    // stream 必须设置为 True，否则会报错
    stream: true,
    stream_options: {
        include_usage: true
    },
    // 开启/关闭思考模式，在思考模式下不支持输出音频；qwen-omni-turbo不支持设置enable_thinking。
    extra_body:{'enable_thinking': true},
    //  设置输出数据的模态，非思考模式下当前支持两种：["text","audio"]、["text"]，思考模式仅支持：["text"]
    modalities: ["text"],
    // 设置音色，思考模式下不支持设置audio参数
    //audio: { voice: "Cherry", format: "wav" }
});

for await (const chunk of completion) {
    if (Array.isArray(chunk.choices) && chunk.choices.length > 0) {
        console.log(chunk.choices[0].delta);
    } else {
        console.log(chunk.usage);
    }
}
```

curl

```
# ======= 重要提示 =======
# 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
# 以下是北京地域base_url，如果使用新加坡地域的模型，需要将base_url替换为：https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions
# === 执行时请删除该注释 ===

curl -X POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions \
-H "Authorization: Bearer $DASHSCOPE_API_KEY" \
-H "Content-Type: application/json" \
-d '{
    "model": "qwen3-omni-flash",
    "messages": [
        {
            "role": "user",
            "content": "你是谁？"
        }
    ],
    "stream":true,
    "stream_options":{
        "include_usage":true
    },
    "modalities":["text"],
    "enable_thinking": true
}'
```

**返回结果**

```
data: {"choices":[{"delta":{"content":null,"role":"assistant","reasoning_content":""},"index":0,"logprobs":null,"finish_reason":null}],"object":"chat.completion.chunk","usage":null,"created":1757937336,"system_fingerprint":null,"model":"qwen3-omni-flash","id":"chatcmpl-ce3d6fe5-e717-4b7e-8b40-3aef12288d4c"}
data: {"choices":[{"finish_reason":null,"logprobs":null,"delta":{"content":null,"reasoning_content":"嗯"},"index":0}],"object":"chat.completion.chunk","usage":null,"reated":1757937336,"system_fingerprint":null,"model":"qwen3-omni-flash","id":"chatcmpl-ce3d6fe5-e717-4b7e-8b40-3aef12288d4c"}
data: {"choices":[{"delta":{"content":null,"reasoning_content":"，"},"finish_reason":null,"index":0,"logprobs":null}],"object":"chat.completion.chunk","usage":null,"reated":1757937336,"system_fingerprint":null,"model":"qwen3-omni-flash","id":"chatcmpl-ce3d6fe5-e717-4b7e-8b40-3aef12288d4c"}
......
data: {"choices":[{"delta":{"content":"告诉我"},"finish_reason":null,"index":0,"logprobs":null}],"object":"chat.completion.chunk","usage":null,"created":1757937336,"tem_fingerprint":null,"model":"qwen3-omni-flash","id":"chatcmpl-ce3d6fe5-e717-4b7e-8b40-3aef12288d4c"}
data: {"choices":[{"delta":{"content":"！"},"finish_reason":null,"index":0,"logprobs":null}],"object":"chat.completion.chunk","usage":null,"created":1757937336,"systm_fingerprint":null,"model":"qwen3-omni-flash","id":"chatcmpl-ce3d6fe5-e717-4b7e-8b40-3aef12288d4c"}
data: {"choices":[{"finish_reason":"stop","delta":{"content":"","reasoning_content":null},"index":0,"logprobs":null}],"object":"chat.completion.chunk","usage":null,"created":1757937336,"system_fingerprint":null,"model":"qwen3-omni-flash","id":"chatcmpl-ce3d6fe5-e717-4b7e-8b40-3aef12288d4c"}
data: {"choices":[],"object":"chat.completion.chunk","usage":{"prompt_tokens":11,"completion_tokens":363,"total_tokens":374,"completion_tokens_details":{"reasoning_tokens":195,"text_tokens":168},"prompt_tokens_details":{"text_tokens":11}},"created":1757937336,"system_fingerprint":null,"model":"qwen3-omni-flash","id":"chatcmpl-ce3d6fe5-e717-4b7e-8b40-3aef12288d4c"}
```

## **图片+文本输入**

Qwen-Omni 模型支持传入多张图片。对输入图片的要求如下：

-   单个图片文件的大小不超过10 MB;
    
-   图片数量：以公网 URL 或本地路径传入时，最多 2048 张；以 Base64 编码传入时，最多 250 张；
    
    > 同时受模型图文总 Token 上限（即最大输入）的限制，所有图片的总 Token 数必须小于模型的最大输入
    
-   图片的宽度和高度均应大于10像素，宽高比不应超过200:1或1:200；
    
-   支持的图片类型请参见[图像与视频理解](https://help.aliyun.com/zh/model-studio/vision#afa499b5b1rl5)。
    

以下示例代码以传入图片公网 URL 为例，传入本地图片请参见：[输入 Base64 编码的本地文件](#c516d1e824x03)。当前只支持以流式输出的方式进行调用。

## OpenAI 兼容

Python

```
import os
from openai import OpenAI

client = OpenAI(
    # 若没有配置环境变量，请用阿里云百炼API Key将下行替换为：api_key="sk-xxx",
    # 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    # 以下是北京地域base_url，如果使用新加坡地域的模型，需要将base_url替换为：https://dashscope-intl.aliyuncs.com/compatible-mode/v1
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

completion = client.chat.completions.create(
    model="qwen3-omni-flash", # 模型为Qwen3-Omni-Flash时，请在非思考模式下运行
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20241022/emyrja/dog_and_girl.jpeg"
                    },
                },
                {"type": "text", "text": "图中描绘的是什么景象？"},
            ],
        },
    ],
    # 设置输出数据的模态，当前支持两种：["text","audio"]、["text"]
    modalities=["text", "audio"],
    audio={"voice": "Cherry", "format": "wav"},
    # stream 必须设置为 True，否则会报错
    stream=True,
    stream_options={
        "include_usage": True
    }
)

for chunk in completion:
    if chunk.choices:
        print(chunk.choices[0].delta)
    else:
        print(chunk.usage)
```

Node.js

```
import OpenAI from "openai";

const openai = new OpenAI(
    {
        // 若没有配置环境变量，请用阿里云百炼API Key将下行替换为：apiKey: "sk-xxx",
        // 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
        apiKey: process.env.DASHSCOPE_API_KEY,
        // 以下是北京地域base_url，如果使用新加坡地域的模型，需要将base_url替换为：https://dashscope-intl.aliyuncs.com/compatible-mode/v1
        baseURL: "https://dashscope.aliyuncs.com/compatible-mode/v1"
    }
);
const completion = await openai.chat.completions.create({
    // 模型为Qwen3-Omni-Flash时，请在非思考模式下运行
    model: "qwen3-omni-flash", 
    messages: [
        {
            "role": "user",
            "content": [{
                "type": "image_url",
                "image_url": { "url": "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20241022/emyrja/dog_and_girl.jpeg" },
            },
            { "type": "text", "text": "图中描绘的是什么景象？" }]
        }],
    stream: true,
    stream_options: {
        include_usage: true
    },
    modalities: ["text", "audio"],
    audio: { voice: "Cherry", format: "wav" }
});

for await (const chunk of completion) {
    if (Array.isArray(chunk.choices) && chunk.choices.length > 0) {
        console.log(chunk.choices[0].delta);
    } else {
        console.log(chunk.usage);
    }
}
```

curl

```
# ======= 重要提示 =======
# 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
# 以下是北京地域base_url，如果使用新加坡地域的模型，需要将base_url替换为：https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions
# === 执行时请删除该注释 ===

curl -X POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions \
-H "Authorization: Bearer $DASHSCOPE_API_KEY" \
-H "Content-Type: application/json" \
-d '{
    "model": "qwen3-omni-flash",
    "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "image_url",
          "image_url": {
            "url": "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20241022/emyrja/dog_and_girl.jpeg"
          }
        },
        {
          "type": "text",
          "text": "图中描绘的是什么景象？"
        }
      ]
    }
  ],
    "stream":true,
    "stream_options":{
        "include_usage":true
    },
    "modalities":["text","audio"],
    "audio":{"voice":"Cherry","format":"wav"}
}'
```

## **音频+文本输入**

-   仅支持输入一个音频文件；
    
-   文件大小：
    
    -   Qwen3-Omni-Flash：不能超过  100MB，时长最长 20 分钟。
        
    -   Qwen-Omni-Turbo：不能超过 10MB，时长最长 3 分钟。
        
-   文件格式：支持AMR、 WAV、 3GP、 3GPP、 AAC、 MP3等主流格式
    

以下示例代码以传入音频公网 URL 为例，传入本地音频请参见：[输入 Base64 编码的本地文件](#c516d1e824x03)。当前只支持以流式输出的方式进行调用。

## OpenAI 兼容

Python

```
import os
from openai import OpenAI

# 初始化OpenAI客户端
client = OpenAI(
    # 若没有配置环境变量，请用阿里云百炼API Key将下行替换为：api_key="sk-xxx",
    # 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    # 以下是北京地域base_url，如果使用新加坡地域的模型，需要将base_url替换为：https://dashscope-intl.aliyuncs.com/compatible-mode/v1
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

completion = client.chat.completions.create(
    model="qwen3-omni-flash", # 模型为Qwen3-Omni-Flash时，请在非思考模式下运行
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "input_audio",
                    "input_audio": {
                        "data": "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20250211/tixcef/cherry.wav",
                        "format": "wav",
                    },
                },
                {"type": "text", "text": "这段音频在说什么"},
            ],
        },
    ],
    # 设置输出数据的模态，当前支持两种：["text","audio"]、["text"]
    modalities=["text", "audio"],
    audio={"voice": "Cherry", "format": "wav"},
    # stream 必须设置为 True，否则会报错
    stream=True,
    stream_options={"include_usage": True},
)

for chunk in completion:
    print(chunk)
    # if chunk.choices:
    #     print(chunk.choices[0].delta)
    # else:
    #     print(chunk.usage)
```

Node.js

```
import OpenAI from "openai";

// 初始化 openai 客户端
const openai = new OpenAI({
     // 若没有配置环境变量，请用阿里云百炼API Key将下行替换为：apiKey:"sk-xxx",
    // 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
    apiKey: process.env.DASHSCOPE_API_KEY, 
    // 以下是北京地域base_url，如果使用新加坡地域的模型，需要将base_url替换为：https://dashscope-intl.aliyuncs.com/compatible-mode/v1
    baseURL: 'https://dashscope.aliyuncs.com/compatible-mode/v1'
});

const completion = await openai.chat.completions.create({
    model: "qwen3-omni-flash",  // 模型为Qwen3-Omni-Flash时，请在非思考模式下运行
    messages: [
        {
            "role": "user",
            "content": [{
                "type": "input_audio",
                "input_audio": { "data": "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20250211/tixcef/cherry.wav", "format": "wav" },
            },
            { "type": "text", "text": "这段音频在说什么" }]
        }],
    stream: true,
    stream_options: {
        include_usage: true
    },
    modalities: ["text", "audio"],
    audio: { voice: "Cherry", format: "wav" }
});

for await (const chunk of completion) {
    if (Array.isArray(chunk.choices) && chunk.choices.length > 0) {
        console.log(chunk.choices[0].delta);
    } else {
        console.log(chunk.usage);
    }
}
```

curl

```
# ======= 重要提示 =======
# 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
# 以下是北京地域base_url，如果使用新加坡地域的模型，需要将base_url替换为：https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions
# === 执行时请删除该注释 ===

curl -X POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions \
-H "Authorization: Bearer $DASHSCOPE_API_KEY" \
-H "Content-Type: application/json" \
-d '{
    "model": "qwen3-omni-flash",
    "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "input_audio",
          "input_audio": {
            "data": "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20250211/tixcef/cherry.wav",
            "format": "wav"
          }
        },
        {
          "type": "text",
          "text": "这段音频在说什么"
        }
      ]
    }
  ],
    "stream":true,
    "stream_options":{
        "include_usage":true
    },
    "modalities":["text","audio"],
    "audio":{"voice":"Cherry","format":"wav"}
}'
```

## **视频+文本输入**

视频的传入方式可以为[图片列表形式](#0f4360d63a8nk)或[视频文件形式（可理解视频中的音频）](#5ed48035d09so)。

以下示例代码以传入视频公网 URL 为例，传入本地视频请参见：[输入 Base64 编码的本地文件](#c516d1e824x03)。当前只支持以流式输出的方式进行调用。

#### **图片列表形式**

**图片数量**

-   Qwen3-Omni-Flash：最少传入 2 张图片，最多可传入 128 张图片。
    
-   Qwen-Omni-Turbo：最少传入 4 张图片，最多可传入 80 张图片。
    

## OpenAI 兼容

Python

```
import os
from openai import OpenAI

# 初始化OpenAI客户端
client = OpenAI(
    # 若没有配置环境变量，请用阿里云百炼API Key将下行替换为：api_key="sk-xxx",
    # 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    # 以下是北京地域base_url，如果使用新加坡地域的模型，需要将base_url替换为：https://dashscope-intl.aliyuncs.com/compatible-mode/v1
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

completion = client.chat.completions.create(
    model="qwen3-omni-flash", # 模型为Qwen3-Omni-Flash时，请在非思考模式下运行
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "video",
                    "video": [
                        "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20241108/xzsgiz/football1.jpg",
                        "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20241108/tdescd/football2.jpg",
                        "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20241108/zefdja/football3.jpg",
                        "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20241108/aedbqh/football4.jpg",
                    ],
                },
                {"type": "text", "text": "描述这个视频的具体过程"},
            ],
        }
    ],
    # 设置输出数据的模态，当前支持两种：["text","audio"]、["text"]
    modalities=["text", "audio"],
    audio={"voice": "Cherry", "format": "wav"},
    # stream 必须设置为 True，否则会报错
    stream=True,
    stream_options={"include_usage": True},
)

for chunk in completion:
    if chunk.choices:
        print(chunk.choices[0].delta)
    else:
        print(chunk.usage)
```

Node.js

```
import OpenAI from "openai";

const openai = new OpenAI({
     // 若没有配置环境变量，请用阿里云百炼API Key将下行替换为：apiKey: "sk-xxx",
    // 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
    apiKey: process.env.DASHSCOPE_API_KEY, 
    // 以下是北京地域base_url，如果使用新加坡地域的模型，需要将base_url替换为：https://dashscope-intl.aliyuncs.com/compatible-mode/v1
    baseURL: 'https://dashscope.aliyuncs.com/compatible-mode/v1'
});


const completion = await openai.chat.completions.create({
    model: "qwen3-omni-flash",  // 模型为Qwen3-Omni-Flash时，请在非思考模式下运行
    messages: [{
        role: "user",
        content: [
            {
                type: "video",
                video: [
                    "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20241108/xzsgiz/football1.jpg",
                    "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20241108/tdescd/football2.jpg",
                    "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20241108/zefdja/football3.jpg",
                    "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20241108/aedbqh/football4.jpg"
                ]
            },
            {
                type: "text",
                text: "描述这个视频的具体过程"
            }
        ]
    }],
    stream: true,
    stream_options: {
        include_usage: true
    },
    modalities: ["text", "audio"],
    audio: { voice: "Cherry", format: "wav" }
});

for await (const chunk of completion) {
    if (Array.isArray(chunk.choices) && chunk.choices.length > 0) {
        console.log(chunk.choices[0].delta);
    } else {
        console.log(chunk.usage);
    }
}
```

curl

```
# ======= 重要提示 =======
# 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
# 以下是北京地域base_url，如果使用新加坡地域的模型，需要将base_url替换为：https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions
# === 执行时请删除该注释 ===

curl -X POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions \
-H "Authorization: Bearer $DASHSCOPE_API_KEY" \
-H "Content-Type: application/json" \
-d '{
    "model": "qwen3-omni-flash",
    "messages": [
        {
            "role": "user",
            "content": [
                {
                    "type": "video",
                    "video": [
                        "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20241108/xzsgiz/football1.jpg",
                        "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20241108/tdescd/football2.jpg",
                        "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20241108/zefdja/football3.jpg",
                        "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20241108/aedbqh/football4.jpg"
                    ]
                },
                {
                    "type": "text",
                    "text": "描述这个视频的具体过程"
                }
            ]
        }
    ],
    "stream": true,
    "stream_options": {
        "include_usage": true
    },
    "modalities": ["text", "audio"],
    "audio": {
        "voice": "Cherry",
        "format": "wav"
    }
}'
```

#### **视频文件形式（可理解视频中的音频）**

-   仅支持输入一个视频文件；
    
-   文件大小：
    
    -   Qwen3-Omni-Flash：限制为 256 MB，时长限制为 150s；
        
    -   Qwen-Omni-Turbo：限制为 150 MB，时长限制为 40s；
        
-   文件格式：MP4、AVI、MKV、MOV、FLV、WMV 等。
    
-   视频文件中的视觉信息与音频信息会分开计费。
    

## OpenAI 兼容

Python

```
import os
from openai import OpenAI

client = OpenAI(
    # 若没有配置环境变量，请用阿里云百炼API Key将下行替换为：api_key="sk-xxx",
    # 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    # 以下是北京地域base_url，如果使用新加坡地域的模型，需要将base_url替换为：https://dashscope-intl.aliyuncs.com/compatible-mode/v1
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

completion = client.chat.completions.create(
    model="qwen3-omni-flash", # 模型为Qwen3-Omni-Flash时，请在非思考模式下运行
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "video_url",
                    "video_url": {
                        "url": "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20241115/cqqkru/1.mp4"
                    },
                },
                {"type": "text", "text": "视频的内容是什么?"},
            ],
        },
    ],
    # 设置输出数据的模态，当前支持两种：["text","audio"]、["text"]
    modalities=["text", "audio"],
    audio={"voice": "Cherry", "format": "wav"},
    # stream 必须设置为 True，否则会报错
    stream=True,
    stream_options={"include_usage": True},
)

for chunk in completion:
    if chunk.choices:
        print(chunk.choices[0].delta)
    else:
        print(chunk.usage)
```

Node.js

```
import OpenAI from "openai";

const openai = new OpenAI({
     // 若没有配置环境变量，请用阿里云百炼API Key将下行替换为：apiKey: "sk-xxx",
    // 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
    apiKey: process.env.DASHSCOPE_API_KEY, 
    // 以下是北京地域base_url，如果使用新加坡地域的模型，需要将base_url替换为：https://dashscope-intl.aliyuncs.com/compatible-mode/v1
    baseURL: 'https://dashscope.aliyuncs.com/compatible-mode/v1'
});

const completion = await openai.chat.completions.create({
    model: "qwen3-omni-flash",  // 模型为Qwen3-Omni-Flash时，请在非思考模式下运行
    messages: [
        {
            "role": "user",
            "content": [{
                "type": "video_url",
                "video_url": { "url": "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20241115/cqqkru/1.mp4" },
            },
            { "type": "text", "text": "视频的内容是什么?" }]
        }],
    stream: true,
    stream_options: {
        include_usage: true
    },
    modalities: ["text", "audio"],
    audio: { voice: "Cherry", format: "wav" }
});


for await (const chunk of completion) {
    if (Array.isArray(chunk.choices) && chunk.choices.length > 0) {
        console.log(chunk.choices[0].delta);
    } else {
        console.log(chunk.usage);
    }
}
```

curl

```
# ======= 重要提示 =======
# 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
# 以下是北京地域base_url，如果使用新加坡地域的模型，需要将base_url替换为：https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions
# === 执行时请删除该注释 ===

curl -X POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions \
-H "Authorization: Bearer $DASHSCOPE_API_KEY" \
-H "Content-Type: application/json" \
-d '{
    "model": "qwen3-omni-flash",
    "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "video_url",
          "video_url": {
            "url": "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20241115/cqqkru/1.mp4"
          }
        },
        {
          "type": "text",
          "text": "视频的内容是什么"
        }
      ]
    }
  ],
    "stream":true,
    "stream_options": {
        "include_usage": true
    },
    "modalities":["text","audio"],
    "audio":{"voice":"Cherry","format":"wav"}
}'
```

## **多轮对话**

您在使用 Qwen-Omni 模型的多轮对话功能时，需要注意：

-   Assistant Message
    
    添加到 messages 数组中的 Assistant Message 只可以包含文本数据。
    
-   User Message
    
    一条 User Message 只可以包含文本和一种模态的数据，在多轮对话中您可以在不同的 User Message 中输入不同模态的数据。
    

## OpenAI 兼容

Python

```
import os
from openai import OpenAI

# 初始化OpenAI客户端
client = OpenAI(
    # 若没有配置环境变量，请用阿里云百炼API Key将下行替换为：api_key="sk-xxx",
    # 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    # 以下是北京地域base_url，如果使用新加坡地域的模型，需要将base_url替换为：https://dashscope-intl.aliyuncs.com/compatible-mode/v1
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

completion = client.chat.completions.create(
    model="qwen3-omni-flash", # 模型为Qwen3-Omni-Flash时，请在非思考模式下运行
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "input_audio",
                    "input_audio": {
                        "data": "https://dashscope.oss-cn-beijing.aliyuncs.com/audios/welcome.mp3",
                        "format": "mp3",
                    },
                },
                {"type": "text", "text": "这段音频在说什么"},
            ],
        },
        {
            "role": "assistant",
            "content": [{"type": "text", "text": "这段音频在说：欢迎使用阿里云"}],
        },
        {
            "role": "user",
            "content": [{"type": "text", "text": "介绍一下这家公司？"}],
        },
    ],
    # 设置输出数据的模态，当前支持两种：["text","audio"]、["text"]
    modalities=["text"],
    # stream 必须设置为 True，否则会报错
    stream=True,
    stream_options={"include_usage": True},
)

for chunk in completion:
    if chunk.choices:
        print(chunk.choices[0].delta)
    else:
        print(chunk.usage)
```

Node.js

```
import OpenAI from "openai";

const openai = new OpenAI({
     // 若没有配置环境变量，请用阿里云百炼API Key将下行替换为：apiKey: "sk-xxx",
    // 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
    apiKey: process.env.DASHSCOPE_API_KEY, 
    // 以下是北京地域base_url，如果使用新加坡地域的模型，需要将base_url替换为：https://dashscope-intl.aliyuncs.com/compatible-mode/v1
    baseURL: 'https://dashscope.aliyuncs.com/compatible-mode/v1'
});

const completion = await openai.chat.completions.create({
    model: "qwen3-omni-flash",  // 模型为Qwen3-Omni-Flash时，请在非思考模式下运行
    messages: [
        {
            "role": "user",
            "content": [
                {
                    "type": "input_audio",
                    "input_audio": {
                        "data": "https://dashscope.oss-cn-beijing.aliyuncs.com/audios/welcome.mp3",
                        "format": "mp3",
                    },
                },
                { "type": "text", "text": "这段音频在说什么" },
            ],
        },
        {
            "role": "assistant",
            "content": [{ "type": "text", "text": "这段音频在说：欢迎使用阿里云" }],
        },
        {
            "role": "user",
            "content": [{ "type": "text", "text": "介绍一下这家公司？" }]
        }],
    stream: true,
    stream_options: {
        include_usage: true
    },
    modalities: ["text"]
});


for await (const chunk of completion) {
    if (Array.isArray(chunk.choices) && chunk.choices.length > 0) {
        console.log(chunk.choices[0].delta);
    } else {
        console.log(chunk.usage);
    }
}
```

curl

```
# ======= 重要提示 =======
# 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
# 以下是北京地域base_url，如果使用新加坡地域的模型，需要将base_url替换为：https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions
# === 执行时请删除该注释 ===

curl -X POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions \
-H "Authorization: Bearer $DASHSCOPE_API_KEY" \
-H "Content-Type: application/json" \
-d '{
  "model": "qwen3-omni-flash",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "input_audio",
          "input_audio": {
            "data": "https://dashscope.oss-cn-beijing.aliyuncs.com/audios/welcome.mp3"
          }
        },
        {
          "type": "text",
          "text": "这段音频在说什么"
        }
      ]
    },
    {
      "role": "assistant",
      "content": [
        {
          "type": "text",
          "text": "这段音频在说：欢迎使用阿里云"
        }
      ]
    },
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "介绍一下这家公司？"
        }
      ]
    }
  ],
  "stream": true,
  "stream_options": {
    "include_usage": true
  },
  "modalities": ["text"]
}'
```

## **解析输出的Base64 编码的音频数据**

Qwen-Omni 模型输出的音频为流式输出的 Base64 编码数据。您可以在模型生成过程中维护一个字符串变量，将每个返回片段的 Base64 编码添加到字符串变量后，待生成结束后进行 Base64 解码，得到音频文件；也可以将每个返回片段的 Base64 编码数据实时解码并播放。

Python

```
# Installation instructions for pyaudio:
# APPLE Mac OS X
#   brew install portaudio
#   pip install pyaudio
# Debian/Ubuntu
#   sudo apt-get install python-pyaudio python3-pyaudio
#   or
#   pip install pyaudio
# CentOS
#   sudo yum install -y portaudio portaudio-devel && pip install pyaudio
# Microsoft Windows
#   python -m pip install pyaudio

import os
from openai import OpenAI
import base64
import numpy as np
import soundfile as sf

# 初始化OpenAI客户端
client = OpenAI(
    # 若没有配置环境变量，请用阿里云百炼API Key将下行替换为：api_key="sk-xxx",
    # 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    # 以下是北京地域base_url，如果使用新加坡地域的模型，需要将base_url替换为：https://dashscope-intl.aliyuncs.com/compatible-mode/v1
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

completion = client.chat.completions.create(
    model="qwen3-omni-flash", # 模型为Qwen3-Omni-Flash时，请在非思考模式下运行
    messages=[{"role": "user", "content": "你是谁"}],
    # 设置输出数据的模态，当前支持两种：["text","audio"]、["text"]
    modalities=["text", "audio"],
    audio={"voice": "Cherry", "format": "wav"},
    # stream 必须设置为 True，否则会报错
    stream=True,
    stream_options={"include_usage": True},
)

# 方式1: 待生成结束后再进行解码
audio_string = ""
for chunk in completion:
    if chunk.choices:
        if hasattr(chunk.choices[0].delta, "audio"):
            try:
                audio_string += chunk.choices[0].delta.audio["data"]
            except Exception as e:
                print(chunk.choices[0].delta.content)
    else:
        print(chunk.usage)

wav_bytes = base64.b64decode(audio_string)
audio_np = np.frombuffer(wav_bytes, dtype=np.int16)
sf.write("audio_assistant_py.wav", audio_np, samplerate=24000)

# 方式2: 边生成边解码(使用方式2请将方式1的代码进行注释)
# # 初始化 PyAudio
# import pyaudio
# import time
# p = pyaudio.PyAudio()
# # 创建音频流
# stream = p.open(format=pyaudio.paInt16,
#                 channels=1,
#                 rate=24000,
#                 output=True)

# for chunk in completion:
#     if chunk.choices:
#         if hasattr(chunk.choices[0].delta, "audio"):
#             try:
#                 audio_string = chunk.choices[0].delta.audio["data"]
#                 wav_bytes = base64.b64decode(audio_string)
#                 audio_np = np.frombuffer(wav_bytes, dtype=np.int16)
#                 # 直接播放音频数据
#                 stream.write(audio_np.tobytes())
#             except Exception as e:
#                 print(chunk.choices[0].delta.content)

# time.sleep(0.8)
# # 清理资源
# stream.stop_stream()
# stream.close()
# p.terminate()
```

Node.js

```
// 运行前的准备工作:
// Windows/Mac/Linux 通用:
// 1. 确保已安装 Node.js (建议版本 >= 14)
// 2. 运行以下命令安装必要的依赖:
//    npm install openai wav
// 
// 如果要使用实时播放功能 (方式2), 还需要:
// Windows:
//    npm install speaker
// Mac:
//    brew install portaudio
//    npm install speaker
// Linux (Ubuntu/Debian):
//    sudo apt-get install libasound2-dev
//    npm install speaker

import OpenAI from "openai";

const openai = new OpenAI({
     // 若没有配置环境变量，请用阿里云百炼API Key将下行替换为：apiKey:"sk-xxx",
    // 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
    apiKey: process.env.DASHSCOPE_API_KEY, 
    // 以下是北京地域base_url，如果使用新加坡地域的模型，需要将base_url替换为：https://dashscope-intl.aliyuncs.com/compatible-mode/v1
    baseURL: 'https://dashscope.aliyuncs.com/compatible-mode/v1'
});

const completion = await openai.chat.completions.create({
    model: "qwen3-omni-flash",  //模型为Qwen3-Omni-Flash时，请在非思考模式下运行
    messages: [
        {
            "role": "user",
            "content": "你是谁？"
        }],
    stream: true,
    stream_options: {
        include_usage: true
    },
    modalities: ["text", "audio"],
    audio: { voice: "Cherry", format: "wav" }
});

// 方式1: 待生成结束后再进行解码
// 需要安装: npm install wav
import { createWriteStream } from 'node:fs';  // node:fs 是 Node.js 内置模块，无需安装
import { Writer } from 'wav';

async function convertAudio(audioString, audioPath) {
    try {
        // 解码Base64字符串为Buffer
        const wavBuffer = Buffer.from(audioString, 'base64');
        // 创建WAV文件写入流
        const writer = new Writer({
            sampleRate: 24000,  // 采样率
            channels: 1,        // 单声道
            bitDepth: 16        // 16位深度
        });
        // 创建输出文件流并建立管道连接
        const outputStream = createWriteStream(audioPath);
        writer.pipe(outputStream);

        // 写入PCM数据并结束写入
        writer.write(wavBuffer);
        writer.end();

        // 使用Promise等待文件写入完成
        await new Promise((resolve, reject) => {
            outputStream.on('finish', resolve);
            outputStream.on('error', reject);
        });

        // 添加额外等待时间确保音频完整
        await new Promise(resolve => setTimeout(resolve, 800));

        console.log(`音频文件已成功保存为 ${audioPath}`);
    } catch (error) {
        console.error('处理过程中发生错误:', error);
    }
}

let audioString = "";
for await (const chunk of completion) {
    if (Array.isArray(chunk.choices) && chunk.choices.length > 0) {
        if (chunk.choices[0].delta.audio) {
            if (chunk.choices[0].delta.audio["data"]) {
                audioString += chunk.choices[0].delta.audio["data"];
            }
        }
    } else {
        console.log(chunk.usage);
    }
}
// 执行转换
convertAudio(audioString, "audio_assistant_mjs.wav");


// 方式2: 边生成边实时播放
// 需要先按照上方系统对应的说明安装必要组件
// import Speaker from 'speaker'; // 引入音频播放库

// // 创建扬声器实例（配置与 WAV 文件参数一致）
// const speaker = new Speaker({
//     sampleRate: 24000,  // 采样率
//     channels: 1,        // 声道数
//     bitDepth: 16,       // 位深
//     signed: true        // 有符号 PCM
// });
// for await (const chunk of completion) {
//     if (Array.isArray(chunk.choices) && chunk.choices.length > 0) {
//         if (chunk.choices[0].delta.audio) {
//             if (chunk.choices[0].delta.audio["data"]) {
//                 const pcmBuffer = Buffer.from(chunk.choices[0].delta.audio.data, 'base64');
//                 // 直接写入扬声器播放
//                 speaker.write(pcmBuffer);
//             }
//         }
//     } else {
//         console.log(chunk.usage);
//     }
// }
// speaker.on('finish', () => console.log('播放完成'));
// speaker.end(); // 根据实际 API 流结束情况调用
```

## **输入 Base64 编码的本地文件**

## 图片

以保存在本地的[eagle.png](https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20250326/nlgymo/eagle.png)为例。

Python

```
import os
from openai import OpenAI
import base64

client = OpenAI(
    # 若没有配置环境变量，请用阿里云百炼API Key将下行替换为：api_key="sk-xxx",
    # 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    # 以下是北京地域base_url，如果使用新加坡地域的模型，需要将base_url替换为：https://dashscope-intl.aliyuncs.com/compatible-mode/v1
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)


#  Base64 编码格式
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


base64_image = encode_image("eagle.png")

completion = client.chat.completions.create(
    model="qwen3-omni-flash",# 模型为Qwen3-Omni-Flash时，请在非思考模式下运行
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{base64_image}"},
                },
                {"type": "text", "text": "图中描绘的是什么景象？"},
            ],
        },
    ],
    # 设置输出数据的模态，当前支持两种：["text","audio"]、["text"]
    modalities=["text", "audio"],
    audio={"voice": "Cherry", "format": "wav"},
    # stream 必须设置为 True，否则会报错
    stream=True,
    stream_options={"include_usage": True},
)

for chunk in completion:
    if chunk.choices:
        print(chunk.choices[0].delta)
    else:
        print(chunk.usage)
```

Node.js

```
import OpenAI from "openai";
import { readFileSync } from 'fs';

const openai = new OpenAI({
     // 若没有配置环境变量，请用阿里云百炼API Key将下行替换为：apiKey: "sk-xxx",
    // 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
    apiKey: process.env.DASHSCOPE_API_KEY, 
    // 以下是北京地域base_url，如果使用新加坡地域的模型，需要将base_url替换为：https://dashscope-intl.aliyuncs.com/compatible-mode/v1
    baseURL: 'https://dashscope.aliyuncs.com/compatible-mode/v1'
});

const encodeImage = (imagePath) => {
    const imageFile = readFileSync(imagePath);
    return imageFile.toString('base64');
};
const base64Image = encodeImage("eagle.png")

const completion = await openai.chat.completions.create({
    model: "qwen3-omni-flash",  // 模型为Qwen3-Omni-Flash时，请在非思考模式下运行
    messages: [
        {
            "role": "user",
            "content": [{
                "type": "image_url",
                "image_url": { "url": `data:image/png;base64,${base64Image}` },
            },
            { "type": "text", "text": "图中描绘的是什么景象？" }]
        }],
    stream: true,
    stream_options: {
        include_usage: true
    },
    modalities: ["text", "audio"],
    audio: { voice: "Cherry", format: "wav" }
});

for await (const chunk of completion) {
    if (Array.isArray(chunk.choices) && chunk.choices.length > 0) {
        console.log(chunk.choices[0].delta);
    } else {
        console.log(chunk.usage);
    }
}
```

## 音频

以保存在本地的[welcome.mp3](https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20250214/pijhos/welcome.mp3)为例。

Python

```
import os
from openai import OpenAI
import base64
import numpy as np
import soundfile as sf
import requests

client = OpenAI(
    # 若没有配置环境变量，请用阿里云百炼API Key将下行替换为：api_key="sk-xxx",
    # 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    # 以下是北京地域base_url，如果使用新加坡地域的模型，需要将base_url替换为：https://dashscope-intl.aliyuncs.com/compatible-mode/v1
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)


def encode_audio(audio_path):
    with open(audio_path, "rb") as audio_file:
        return base64.b64encode(audio_file.read()).decode("utf-8")


base64_audio = encode_audio("welcome.mp3")

completion = client.chat.completions.create(
    model="qwen3-omni-flash", # 模型为Qwen3-Omni-Flash时，请在非思考模式下运行
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "input_audio",
                    "input_audio": {
                        "data": f"data:;base64,{base64_audio}",
                        "format": "mp3",
                    },
                },
                {"type": "text", "text": "这段音频在说什么"},
            ],
        },
    ],
    # 设置输出数据的模态，当前支持两种：["text","audio"]、["text"]
    modalities=["text", "audio"],
    audio={"voice": "Cherry", "format": "wav"},
    # stream 必须设置为 True，否则会报错
    stream=True,
    stream_options={"include_usage": True},
)

for chunk in completion:
    if chunk.choices:
        print(chunk.choices[0].delta)
    else:
        print(chunk.usage)
```

Node.js

```
import OpenAI from "openai";
import { readFileSync } from 'fs';

const openai = new OpenAI({
     // 若没有配置环境变量，请用阿里云百炼API Key将下行替换为：apiKey: "sk-xxx",
    // 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
    apiKey: process.env.DASHSCOPE_API_KEY, 
    // 以下是北京地域base_url，如果使用新加坡地域的模型，需要将base_url替换为：https://dashscope-intl.aliyuncs.com/compatible-mode/v1
    baseURL: 'https://dashscope.aliyuncs.com/compatible-mode/v1'
});

const encodeAudio = (audioPath) => {
    const audioFile = readFileSync(audioPath);
    return audioFile.toString('base64');
};
const base64Audio = encodeAudio("welcome.mp3")

const completion = await openai.chat.completions.create({
    model: "qwen3-omni-flash",  // 模型为Qwen3-Omni-Flash时，请在非思考模式下运行
    messages: [
        {
            "role": "user",
            "content": [{
                "type": "input_audio",
                "input_audio": { "data": `data:;base64,${base64Audio}`, "format": "mp3" },
            },
            { "type": "text", "text": "这段音频在说什么" }]
        }],
    stream: true,
    stream_options: {
        include_usage: true
    },
    modalities: ["text", "audio"],
    audio: { voice: "Cherry", format: "wav" }
});

for await (const chunk of completion) {
    if (Array.isArray(chunk.choices) && chunk.choices.length > 0) {
        console.log(chunk.choices[0].delta);
    } else {
        console.log(chunk.usage);
    }
}
```

## 视频

## 视频文件

以保存在本地的[spring\_mountain.mp4](https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20250326/fqojlv/spring_mountain.mp4)为例。

Python

```
import os
from openai import OpenAI
import base64
import numpy as np
import soundfile as sf

client = OpenAI(
    # 若没有配置环境变量，请用阿里云百炼API Key将下行替换为：api_key="sk-xxx",
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)


#  Base64 编码格式
def encode_video(video_path):
    with open(video_path, "rb") as video_file:
        return base64.b64encode(video_file.read()).decode("utf-8")


base64_video = encode_video("spring_mountain.mp4")

completion = client.chat.completions.create(
    model="qwen3-omni-flash", # 模型为Qwen3-Omni-Flash时，请在非思考模式下运行
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "video_url",
                    "video_url": {"url": f"data:;base64,{base64_video}"},
                },
                {"type": "text", "text": "她在唱什么"},
            ],
        },
    ],
    # 设置输出数据的模态，当前支持两种：["text","audio"]、["text"]
    modalities=["text", "audio"],
    audio={"voice": "Cherry", "format": "wav"},
    # stream 必须设置为 True，否则会报错
    stream=True,
    stream_options={"include_usage": True},
)

for chunk in completion:
    if chunk.choices:
        print(chunk.choices[0].delta)
    else:
        print(chunk.usage)
```

Node.js

```
import OpenAI from "openai";
import { readFileSync } from 'fs';

const openai = new OpenAI(
    {
        // 若没有配置环境变量，请用阿里云百炼API Key将下行替换为：apiKey: "sk-xxx",
        apiKey: process.env.DASHSCOPE_API_KEY,
        baseURL: "https://dashscope.aliyuncs.com/compatible-mode/v1"
    }
);

const encodeVideo = (videoPath) => {
    const videoFile = readFileSync(videoPath);
    return videoFile.toString('base64');
};
const base64Video = encodeVideo("spring_mountain.mp4")

const completion = await openai.chat.completions.create({
    model: "qwen3-omni-flash",  // 模型为Qwen3-Omni-Flash时，请在非思考模式下运行
    messages: [
        {
            "role": "user",
            "content": [{
                "type": "video_url",
                "video_url": { "url": `data:;base64,${base64Video}` },
            },
            { "type": "text", "text": "她在唱什么" }]
        }],
    stream: true,
    stream_options: {
        include_usage: true
    },
    modalities: ["text", "audio"],
    audio: { voice: "Cherry", format: "wav" }
});

for await (const chunk of completion) {
    if (Array.isArray(chunk.choices) && chunk.choices.length > 0) {
        console.log(chunk.choices[0].delta);
    } else {
        console.log(chunk.usage);
    }
}
```

## 图片列表

以保存在本地的[football1.jpg](https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20250319/vzfwkh/football1.jpg)、[football2.jpg](https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20250319/vgkgqy/football2.jpg)、[football3.jpg](https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20250127/fytnla/football3.jpg)与[football4.jpg](https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20250127/ygitwp/football4.jpg)为例。

Python

```
import os
from openai import OpenAI
import base64
import numpy as np
import soundfile as sf

client = OpenAI(
    # 若没有配置环境变量，请用阿里云百炼API Key将下行替换为：api_key="sk-xxx",
    # 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    # 以下是北京地域base_url，如果使用新加坡地域的模型，需要将base_url替换为：https://dashscope-intl.aliyuncs.com/compatible-mode/v1
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)


#  Base64 编码格式
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


base64_image_1 = encode_image("football1.jpg")
base64_image_2 = encode_image("football2.jpg")
base64_image_3 = encode_image("football3.jpg")
base64_image_4 = encode_image("football4.jpg")

completion = client.chat.completions.create(
    model="qwen3-omni-flash",  # 模型为Qwen3-Omni-Flash时，请在非思考模式下运行
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "video",
                    "video": [
                        f"data:image/jpeg;base64,{base64_image_1}",
                        f"data:image/jpeg;base64,{base64_image_2}",
                        f"data:image/jpeg;base64,{base64_image_3}",
                        f"data:image/jpeg;base64,{base64_image_4}",
                    ],
                },
                {"type": "text", "text": "描述这个视频的具体过程"},
            ],
        }
    ],
    # 设置输出数据的模态，当前支持两种：["text","audio"]、["text"]
    modalities=["text", "audio"],
    audio={"voice": "Cherry", "format": "wav"},
    # stream 必须设置为 True，否则会报错
    stream=True,
    stream_options={"include_usage": True},
)

for chunk in completion:
    if chunk.choices:
        print(chunk.choices[0].delta)
    else:
        print(chunk.usage)
```

Node.js

```
import OpenAI from "openai";
import { readFileSync } from 'fs';

const openai = new OpenAI({
     // 若没有配置环境变量，请用阿里云百炼API Key将下行替换为：apiKey: "sk-xxx",
    // 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
    apiKey: process.env.DASHSCOPE_API_KEY, 
    // 以下是北京地域base_url，如果使用新加坡地域的模型，需要将base_url替换为：https://dashscope-intl.aliyuncs.com/compatible-mode/v1
    baseURL: 'https://dashscope.aliyuncs.com/compatible-mode/v1'
});

const encodeImage = (imagePath) => {
    const imageFile = readFileSync(imagePath);
    return imageFile.toString('base64');
  };
const base64Image1 = encodeImage("football1.jpg")
const base64Image2 = encodeImage("football2.jpg")
const base64Image3 = encodeImage("football3.jpg")
const base64Image4 = encodeImage("football4.jpg")

const completion = await openai.chat.completions.create({
    model: "qwen3-omni-flash",  // 模型为Qwen3-Omni-Flash时，请在非思考模式下运行
    messages: [{
        role: "user",
        content: [
            {
                type: "video",
                video: [
                    `data:image/jpeg;base64,${base64Image1}`,
                    `data:image/jpeg;base64,${base64Image2}`,
                    `data:image/jpeg;base64,${base64Image3}`,
                    `data:image/jpeg;base64,${base64Image4}`
                ]
            },
            {
                type: "text",
                text: "描述这个视频的具体过程"
            }
        ]
    }],
    stream: true,
    stream_options: {
        include_usage: true
    },
    modalities: ["text", "audio"],
    audio: { voice: "Cherry", format: "wav" }
});

for await (const chunk of completion) {
    if (Array.isArray(chunk.choices) && chunk.choices.length > 0) {
        console.log(chunk.choices[0].delta);
    } else {
        console.log(chunk.usage);
    }
}
```

## API参考

关于千问Omni 模型的输入输出参数，请参见[千问](https://help.aliyun.com/zh/model-studio/qwen-api-reference/)。

## 计费与限流

**计费规则**

Qwen-Omni模型根据不同模态（音频、图像、视频）对应的Token数计费。计费详情请参见[模型列表](https://help.aliyun.com/zh/model-studio/models#90e80b9e42ged)。

**音频、图片与视频转换为Token数的规则**

## 音频

-   `Qwen3-Omni-Flash：总 Tokens 数 = 音频时长（单位：秒）* 12.5`
    
-   `Qwen-Omni-Turbo：总 Tokens 数 = 音频时长（单位：秒）* 25`，若音频时长不足1秒，则按 1 秒计算。
    

## 图片

-   `Qwen3-Omni-Flash`模型**：**每`32x32`像素对应 1 个 Token
    
-   `Qwen-Omni-Turbo`模型：每`28x28`像素对应 1 个 Token
    

一张图最少需要 4 个 Token，最多支持 1280 个 Token；可使用以下代码，传入图像路径即可估算单张图片消耗的 Token 总量：

```
import math
# 使用以下命令安装Pillow库：pip install Pillow
from PIL import Image

# Qwen-Omni-Turbo模型，factor为28
# factor = 28
# Qwen3-Omni-Flash模型，factor为32
factor = 32

def token_calculate(image_path=''):
    """
    param image_path: 图像路径
    return: 单张图像的Token数
    """
    if len(image_path) > 0:
        # 打开指定的PNG图片文件
        image = Image.open(image_path)
        # 获取图片的原始尺寸
        height = image.height
        width = image.width
        print(f"缩放前的图像尺寸为：高度为{height}，宽度为{width}")
        # 将高度调整为factor的整数倍
        h_bar = round(height / factor) * factor
        # 将宽度调整为factor的整数倍
        w_bar = round(width / factor) * factor
        # 图像的Token下限：4个Token
        min_pixels = 4 * factor * factor
        # 图像的Token上限：1280个Token
        max_pixels = 1280 * factor * factor
        # 对图像进行缩放处理，调整像素的总数在范围[min_pixels,max_pixels]内
        if h_bar * w_bar > max_pixels:
            # 计算缩放因子beta，使得缩放后的图像总像素数不超过max_pixels
            beta = math.sqrt((height * width) / max_pixels)
            # 重新计算调整后的高度，确保为factor的整数倍
            h_bar = math.floor(height / beta / factor) * factor
            # 重新计算调整后的宽度，确保为factor的整数倍
            w_bar = math.floor(width / beta / factor) * factor
        elif h_bar * w_bar < min_pixels:
            # 计算缩放因子beta，使得缩放后的图像总像素数不低于min_pixels
            beta = math.sqrt(min_pixels / (height * width))
            # 重新计算调整后的高度，确保为factor的整数倍
            h_bar = math.ceil(height * beta / factor) * factor
            # 重新计算调整后的宽度，确保为factor的整数倍
            w_bar = math.ceil(width * beta / factor) * factor
        print(f"缩放后的图像尺寸为：高度为{h_bar}，宽度为{w_bar}")
        # 计算图像的Token数：总像素除以factor * factor
        token = int((h_bar * w_bar) / (factor * factor)) + 2
        print(f"缩放后的token数量为：{token}")
        return token
    else:
        raise ValueError("图像路径不能为空，请提供有效的图像文件路径")
    
if __name__ == "__main__":
    token = token_calculate(image_path="xxx/test.jpg")
```

## 视频

视频文件的 Token 分为 `video_tokens`（视觉）与 `audio_tokens`（音频）。

-   `video_tokens`
    
    计算过程较为复杂。请参见以下代码：
    
    ```
    # 使用前安装：pip install opencv-python
    import math
    import os
    import logging
    import cv2
    
    # 固定参数
    FRAME_FACTOR = 2
    
    # Qwen3-Omni-Flash模型，IMAGE_FACTOR为32
    IMAGE_FACTOR = 32
    
    # Qwen-Omni-Turbo模型，IMAGE_FACTOR为28
    # IMAGE_FACTOR = 28
    
    # 视频帧的长宽比
    MAX_RATIO = 200
    
    # 视频帧的像素下限，Qwen3-Omni-Flash为：128 * 32 * 32
    VIDEO_MIN_PIXELS = 128 * 32 * 32
    # Qwen-Omni-Turbo
    # VIDEO_MIN_PIXELS = 128 * 28 * 28
    
    # 视频帧的像素上限，Qwen3-Omni-Flash为：768 * 32 * 32
    VIDEO_MAX_PIXELS = 768 * 32 * 32
    # Qwen-Omni-Turbo：
    # VIDEO_MAX_PIXELS = 768 * 28 * 28
    
    FPS = 2
    # 最少抽取帧数
    FPS_MIN_FRAMES = 4
    
    # 最大抽取帧数
    # Qwen3-Omni-Flash模型的大抽取帧数：128
    # Qwen3-Omni-Turbo模型的大抽取帧数：80
    FPS_MAX_FRAMES = 128
    
    # 视频输入的最大像素值，Qwen3-Omni-Flash为 16384 * 32 * 32；
    VIDEO_TOTAL_PIXELS = 16384 * 32 * 32
    # Qwen-Omni-Turbo：
    # VIDEO_TOTAL_PIXELS = 16384 * 28 * 28
    
    def round_by_factor(number, factor):
        return round(number / factor) * factor
    
    def ceil_by_factor(number, factor):
        return math.ceil(number / factor) * factor
    
    def floor_by_factor(number, factor):
        return math.floor(number / factor) * factor
    
    def get_video(video_path):
        cap = cv2.VideoCapture(video_path)
        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        video_fps = cap.get(cv2.CAP_PROP_FPS)
        cap.release()
        return frame_height, frame_width, total_frames, video_fps
    
    def smart_nframes(total_frames, video_fps):
        min_frames = ceil_by_factor(FPS_MIN_FRAMES, FRAME_FACTOR)
        max_frames = floor_by_factor(min(FPS_MAX_FRAMES, total_frames), FRAME_FACTOR)
        duration = total_frames / video_fps if video_fps != 0 else 0
        if duration - int(duration) > (1 / FPS):
            total_frames = math.ceil(duration * video_fps)
        else:
            total_frames = math.ceil(int(duration) * video_fps)
        nframes = total_frames / video_fps * FPS
        nframes = int(min(min(max(nframes, min_frames), max_frames), total_frames))
        if not (FRAME_FACTOR <= nframes <= total_frames):
            raise ValueError(f"nframes should in interval [{FRAME_FACTOR}, {total_frames}], but got {nframes}.")
        return nframes
    
    def smart_resize(height, width, nframes, factor=IMAGE_FACTOR):
        min_pixels = VIDEO_MIN_PIXELS
        total_pixels = VIDEO_TOTAL_PIXELS
        max_pixels = max(min(VIDEO_MAX_PIXELS, total_pixels / nframes * FRAME_FACTOR), int(min_pixels * 1.05))
        if max(height, width) / min(height, width) > MAX_RATIO:
            raise ValueError(f"absolute aspect ratio must be smaller than {MAX_RATIO}, got {max(height, width) / min(height, width)}")
        h_bar = max(factor, round_by_factor(height, factor))
        w_bar = max(factor, round_by_factor(width, factor))
        if h_bar * w_bar > max_pixels:
            beta = math.sqrt((height * width) / max_pixels)
            h_bar = floor_by_factor(height / beta, factor)
            w_bar = floor_by_factor(width / beta, factor)
        elif h_bar * w_bar < min_pixels:
            beta = math.sqrt(min_pixels / (height * width))
            h_bar = ceil_by_factor(height * beta, factor)
            w_bar = ceil_by_factor(width * beta, factor)
        return h_bar, w_bar
    
    def video_token_calculate(video_path):
        height, width, total_frames, video_fps = get_video(video_path)
        nframes = smart_nframes(total_frames, video_fps)
        resized_height, resized_width = smart_resize(height, width, nframes)
        video_token = int(math.ceil(nframes / FPS) * resized_height / 32 * resized_width / 32)
        video_token += 2  # 视觉标记
        return video_token
    
    if __name__ == "__main__":
        video_path = "spring_mountain.mp4"  # 你的视频路径
        video_token = video_token_calculate(video_path)
        print("video_tokens:", video_token)
    ```
    
-   `audio_tokens`
    
    -   Qwen3-Omni-Flash：`总Tokens数 = 音频时长（单位：秒）* 12.5`
        
    -   Qwen-Omni-Turbo：`总Tokens数 = 音频时长（单位：秒）* 25`
        
    
    若音频时长不足1秒，则按 1 秒计算。
    

**免费额度**

关于免费额度的领取、查询、使用方法等详情，请参见[新人免费额度](https://help.aliyun.com/zh/model-studio/new-free-quota)。

**限流**

模型限流规则及常见问题，请参见[限流](https://help.aliyun.com/zh/model-studio/rate-limit)。

## **常见问题**

### **Q：如何给 Qwen-Omni-Turbo 模型设置角色？**

A：Qwen-Omni-Turbo模型在输出模态包括音频时**不支持设定 System Message，**即使您在 System Message 中说明：“你是XXX...”等角色信息，Qwen-Omni 的自我认知依然会是千问。

-   **方法1（推荐）：**Qwen3-Omni-Flash模型已支持设定**System Message，**建议切换至该系列模型。
    
-   **方法2：**在messages 数组的开头手动添加用于角色设定的 User Message 和 Assistant Message，达到给 Qwen-Omni 模型设置角色的效果。
    
    **用于角色设定的示例代码**
    
    ## OpenAI 兼容
    
    Python
    
    ```
    import os
    from openai import OpenAI
    
    client = OpenAI(
        # 若没有配置环境变量，请用阿里云百炼API Key将下行替换为：api_key="sk-xxx",
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    
    completion = client.chat.completions.create(
        model="qwen-omni-turbo",
        messages=[
            {"role": "user", "content": "你是一个商场的导购员，你负责的商品有手机、电脑、冰箱"},
            {"role": "assistant", "content": "好的，我记住了你的设定。"},
            {"role": "user", "content": "你是谁"},
        ],
        # 设置输出数据的模态，当前支持两种：["text","audio"]、["text"]
        modalities=["text", "audio"],
        audio={"voice": "Cherry", "format": "wav"},
        # stream 必须设置为 True，否则会报错
        stream=True,
        stream_options={"include_usage": True},
    )
    
    for chunk in completion:
        if chunk.choices:
            print(chunk.choices[0].delta)
        else:
            print(chunk.usage)
    ```
    
    Node.js
    
    ```
    import OpenAI from "openai";
    
    const openai = new OpenAI(
        {
            // 若没有配置环境变量，请用阿里云百炼API Key将下行替换为：apiKey: "sk-xxx",
            apiKey: process.env.DASHSCOPE_API_KEY,
            baseURL: "https://dashscope.aliyuncs.com/compatible-mode/v1"
        }
    );
    const completion = await openai.chat.completions.create({
        model: "qwen-omni-turbo",
        messages: [
            { role: "user", content: "你是一个商场的导购员，你负责的商品有手机、电脑、冰箱" },
            { role: "assistant", content: "好的，我记住了你的设定。" },
            { role: "user", content: "你是谁？" }
        ],
        stream: true,
        stream_options: {
            include_usage: true
        },
        modalities: ["text", "audio"],
        audio: { voice: "Cherry", format: "wav" }
    });
    
    for await (const chunk of completion) {
        if (Array.isArray(chunk.choices) && chunk.choices.length > 0) {
            console.log(chunk.choices[0].delta);
        } else {
            console.log(chunk.usage);
        }
    }
    ```
    
    curl
    
    ```
    curl -X POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions \
    -H "Authorization: Bearer $DASHSCOPE_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{
        "model": "qwen-omni-turbo",
        "messages": [
            {
                "role": "user", 
                "content": "你是一个商场的导购员，你负责的商品有手机、电脑、冰箱"
            },
            {
                "role": "assistant", 
                "content": "好的，我记住了你的设定。"
            },
            {
                "role": "user", 
                "content": "你是谁？"
            }
        ],
        "stream":true,
        "stream_options":{
            "include_usage":true
        },
        "modalities":["text","audio"],
        "audio":{"voice":"Cherry","format":"wav"}
    }'
    ```
    

## 错误码

如果模型调用失败并返回报错信息，请参见[错误信息](https://help.aliyun.com/zh/model-studio/error-code)进行解决。

## **音色列表**

> 使用时将请求参数`voice`设置为如下表格的“**voice参数**”列对应的值：

## qwen3-omni-flash-2025-12-01模型

| **音色名** | `**voice**`**参数** | **音色效果** | **描述** | **支持的语种** |
| --- | --- | --- | --- | --- |
| 芊悦  | Cherry |     | 阳光积极、亲切自然小姐姐 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 苏瑶  | Serena |     | 温柔小姐姐 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 晨煦  | Ethan |     | 标准普通话，带部分北方口音。阳光、温暖、活力、朝气 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 千雪  | Chelsie |     | 二次元虚拟女友 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 茉兔  | Momo |     | 撒娇搞怪，逗你开心 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 十三  | Vivian |     | 拽拽的、可爱的小暴躁 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 月白  | Moon |     | 率性帅气的月白 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 四月  | Maia |     | 知性与温柔的碰撞 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 凯   | Kai |     | 耳朵的一场SPA | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 不吃鱼 | Nofish |     | 不会翘舌音的设计师 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 萌宝  | Bella |     | 喝酒不打醉拳的小萝莉 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 詹妮弗 | Jennifer |     | 品牌级、电影质感般美语女声 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 甜茶  | Ryan |     | 节奏拉满，戏感炸裂，真实与张力共舞 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 卡捷琳娜 | Katerina |     | 御姐音色，韵律回味十足 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 艾登  | Aiden |     | 精通厨艺的美语大男孩 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 沧明子 | Eldric Sage |     | 沉稳睿智的老者，沧桑如松却心明如镜 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 乖小妹 | Mia |     | 温顺如春水，乖巧如初雪 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 沙小弥 | Mochi |     | 聪明伶俐的小大人，童真未泯却早慧如禅 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 燕铮莺 | Bellona |     | 声音洪亮，吐字清晰，人物鲜活，听得人热血沸腾； 金戈铁马入梦来，字正腔圆间尽显千面人声的江湖 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 田叔  | Vincent |     | 一口独特的沙哑烟嗓，一开口便道尽了千军万马与江湖豪情 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 萌小姬 | Bunny |     | “萌属性”爆棚的小萝莉 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 阿闻  | Neil |     | 平直的基线语调，字正腔圆的咬字发音，这就是最专业的新闻主持人 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 墨讲师 | Elias |     | 既保持学科严谨性，又通过叙事技巧将复杂知识转化为可消化的认知模块 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 徐大爷 | Arthur |     | 被岁月和旱烟浸泡过的质朴嗓音，不疾不徐地摇开了满村的奇闻异事 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 邻家妹妹 | Nini |     | 糯米糍一样又软又黏的嗓音，那一声声拉长了的“哥哥”，甜得能把人的骨头都叫酥了 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 诡婆婆 | Ebona |     | 她的低语像一把生锈的钥匙，缓慢转动你内心最深处的幽暗角落——那里藏着所有你不敢承认的童年阴影与未知恐惧 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 小婉  | Seren |     | 温和舒缓的声线，助你更快地进入睡眠，晚安，好梦 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 顽屁小孩 | Pip |     | 调皮捣蛋却充满童真的他来了，这是你记忆中的小新吗 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 少女阿月 | Stella |     | 平时是甜到发腻的迷糊少女音，但在喊出“代表月亮消灭你”时，瞬间充满不容置疑的爱与正义 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 博德加 | Bodega |     | 热情的西班牙大叔 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 索尼莎 | Sonrisa |     | 热情开朗的拉美大姐 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 阿列克 | Alek |     | 一开口，是战斗民族的冷，也是毛呢大衣下的暖 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 多尔切 | Dolce |     | 慵懒的意大利大叔 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 素熙  | Sohee |     | 温柔开朗，情绪丰富的韩国欧尼 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 小野杏 | Ono Anna |     | 鬼灵精怪的青梅竹马 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 莱恩  | Lenn |     | 理性是底色，叛逆藏在细节里——穿西装也听后朋克的德国青年 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 埃米尔安 | Emilien |     | 浪漫的法国大哥哥 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 安德雷 | Andre |     | 声音磁性，自然舒服、沉稳男生 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 拉迪奥·戈尔 | Radio Gol |     | 足球诗人Rádio Gol！今天我要用名字为你们解说足球。 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 上海-阿珍 | Jada |     | 风风火火的沪上阿姐 | 中文（上海话）、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 北京-晓东 | Dylan |     | 北京胡同里长大的少年 | 中文（北京话）、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 南京-老李 | Li  |     | 耐心的瑜伽老师 | 中文（南京话）、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 陕西-秦川 | Marcus |     | 面宽话短，心实声沉——老陕的味道 | 中文（陕西话）、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 闽南-阿杰 | Roy |     | 诙谐直爽、市井活泼的台湾哥仔形象 | 中文（闽南语）、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 天津-李彼得 | Peter |     | 天津相声，专业捧哏 | 中文（天津话）、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 四川-晴儿 | Sunny |     | 甜到你心里的川妹子 | 中文（四川话）、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 四川-程川 | Eric |     | 一个跳脱市井的四川成都男子 | 中文（四川话）、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 粤语-阿强 | Rocky |     | 幽默风趣的阿强，在线陪聊 | 中文（粤语）、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 粤语-阿清 | Kiki |     | 甜美的港妹闺蜜 | 中文（粤语）、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |

### qwen3-omni-flash、qwen3-omni-flash-2025-09-15**模型**

| **音色名** | `**voice**`**参数** | **音色效果** | **描述** | **支持的语种** |
| --- | --- | --- | --- | --- |
| 芊悦  | Cherry |     | 阳光积极、亲切自然小姐姐 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 晨煦  | Ethan |     | 标准普通话，带部分北方口音。阳光、温暖、活力、朝气 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 不吃鱼 | Nofish |     | 不会翘舌音的设计师 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 詹妮弗 | Jennifer |     | 品牌级、电影质感般美语女声 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 甜茶  | Ryan |     | 节奏拉满，戏感炸裂，真实与张力共舞 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 卡捷琳娜 | Katerina |     | 御姐音色，韵律回味十足 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 墨讲师 | Elias |     | 既保持学科严谨性，又通过叙事技巧将复杂知识转化为可消化的认知模块 | 中文、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 上海-阿珍 | Jada |     | 风风火火的沪上阿姐 | 中文（上海话）、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 北京-晓东 | Dylan |     | 北京胡同里长大的少年 | 中文（北京话）、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 四川-晴儿 | Sunny |     | 甜到你心里的川妹子 | 中文（四川话）、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 南京-老李 | Li  |     | 耐心的瑜伽老师 | 中文（南京话）、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 陕西-秦川 | Marcus |     | 面宽话短，心实声沉——老陕的味道 | 中文（陕西话）、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 闽南-阿杰 | Roy |     | 诙谐直爽、市井活泼的台湾哥仔形象 | 中文（闽南语）、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 天津-李彼得 | Peter |     | 天津相声，专业捧哏 | 中文（天津话）、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 粤语-阿强 | Rocky |     | 幽默风趣的阿强，在线陪聊 | 中文（粤语）、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 粤语-阿清 | Kiki |     | 甜美的港妹闺蜜 | 中文（粤语）、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |
| 四川-程川 | Eric |     | 一个跳脱市井的四川成都男子 | 中文（四川话）、英语、法语、德语、俄语、意大利语、西班牙语、葡萄牙语、日语、韩语 |

### **Qwen-Omni-Turbo模型**

| **音色名** | `**voice**`**参数** | **音色效果** | **描述** | **支持的语种** |
| --- | --- | --- | --- | --- |
| 芊悦  | Cherry |     | 阳光积极、亲切自然小姐姐 | 中文、英语 |
| 苏瑶  | Serena |     | 温柔小姐姐 | 中文、英语 |
| 晨煦  | Ethan |     | 标准普通话，带部分北方口音。阳光、温暖、活力、朝气 | 中文、英语 |
| 千雪  | Chelsie |     | 二次元虚拟女友 | 中文、英语 |

### **Qwen-Omni 开源模型**

| **音色名** | `**voice**`**参数** | **音色效果** | **描述** | **支持的语种** |
| --- | --- | --- | --- | --- |
| 晨煦  | Ethan |     | 标准普通话，带部分北方口音。阳光、温暖、活力、朝气 | 中文、英语 |
| 千雪  | Chelsie |     | 二次元虚拟女友 | 中文、英语 |

/\* 让引用上下间距调小，避免内容显示过于稀疏 \*/ .unionContainer .markdown-body blockquote { margin: 4px 0; } .aliyun-docs-content table.qwen blockquote { border-left: none; /\* 添加这一行来移除表格里的引用文字的左侧边框 \*/ padding-left: 5px; /\* 左侧内边距 \*/ margin: 4px 0; }