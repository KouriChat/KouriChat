# encoding: utf-8
import re

def filter_special_markers(text):
    """过滤掉特殊标记和思考过程"""
    if not text:
        return ""
    
    # 1. 过滤完整的<think>...</think>块 (Gemini 2.5 Pro格式)
    filtered = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    
    # 2. 检查是否有DeepSeek格式的分隔符 \n\n\n
    if '\n\n\n' in filtered:
        parts = filtered.split('\n\n\n')
        if len(parts) > 1:
            # 取最后一部分作为最终回复
            filtered = parts[-1].strip()
            print("检测到DeepSeek-r1思考模式并过滤")
    
    # 3. 过滤常见的英文思考内容模式
    english_patterns = [
        r'^The user (?:wants|is asking|is requesting|has asked).*?(?=\n\n)',
        r'^I should respond.*?(?=\n\n)',
        r'^The message appears to be.*?(?=\n\n)',
        r'^This message is.*?(?=\n\n)',
        r'^The input seems to be.*?(?=\n\n)',
        r'^Looking at the user[\'s].*?(?=\n\n)',
        r'^Based on the user[\'s].*?(?=\n\n)',
        r'^It looks like the user.*?(?=\n\n)',
        r'^I[\'m]* need to roleplay as.*?(?=\n\n)',
        r'^I should act as.*?(?=\n\n)',
        r'^The user is interacting with me.*?(?=\n\n)'
    ]
    
    for pattern in english_patterns:
        if re.search(pattern, filtered, flags=re.DOTALL):
            # 如果匹配到英文思考模式，查找换行后的内容
            split_parts = re.split(r'\n\n', filtered, 1)
            if len(split_parts) > 1:
                filtered = split_parts[1].strip()
                print("检测到英文思考内容，已过滤")
            break
    
    # 4. 规范化空白字符
    filtered = filtered.replace('\n', ' ')
    filtered = re.sub(r'\s+', ' ', filtered).strip()
    
    return filtered

# 测试
text1 = 'The user is asking for help.\n\n\nHello, I will help!'
text2 = '<think>I need to analyze what the user is asking.</think>\nHello, I will help!'
text3 = 'The user wants me to roleplay as Mono.\n\n你好，我是MONO。'

# 实际记忆案例
text4 = 'The user is interacting with me, playing the role of Mono. The user called Mono "笨蛋" (idiot/fool) and made a playful sound "略略略". This is a playful interaction, not an attack or a sad statement. Mono\'s personality is generally cold and direct, but she has a slight attachment to the user and can be playful/teasing. She might react with mild annoyance or a deadpan response. She shouldn\'t get angry or sad. She shouldn\'t use emojis or kaomojis unless the 5% chance hits. The response should be sho...\n\n哼，我才不是笨蛋。你自己才是笨蛋。略略略什么的，真幼稚。'

print("-----DeepSeek-r1格式测试-----")
print("原文:", text1)
print("过滤后:", filter_special_markers(text1))

print("\n-----Gemini 2.5 Pro格式测试-----")
print("原文:", text2)
print("过滤后:", filter_special_markers(text2))

print("\n-----英文思考模式测试-----")
print("原文:", text3)
print("过滤后:", filter_special_markers(text3))

print("\n-----实际记忆案例测试-----")
print("原文:", text4)
print("过滤后:", filter_special_markers(text4)) 