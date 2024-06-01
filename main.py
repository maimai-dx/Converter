import shutil
import os
import sys
import ffmpeg
import subprocess
import UnityPy
from PIL import Image
from pathlib import Path
from wannacri.wannacri import create_usm
from unittest.mock import patch
from lark import Lark
from transformer import SimaiTransformer
import xmltodict
from xml.etree import ElementTree
from concurrent.futures import ThreadPoolExecutor


def recursive_string_replace(obj, old, new):
    if isinstance(obj, dict):
        for key, value in obj.items():
            obj[key] = recursive_string_replace(value, old, new)
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            obj[index] = recursive_string_replace(value, old, new)
    elif isinstance(obj, tuple):
        new_tuple = []
        for index, value in enumerate(obj):
            new_tuple.append(recursive_string_replace(value, old, new))
        obj = tuple(new_tuple)
    elif isinstance(obj, str):
        if old in obj:
            obj = obj.replace(old, new)
    return obj


def replace_value(obj, target, replacement, visited=None):
    if visited is None:
        visited = set()

    # Prevent infinite recursion on circular references
    if id(obj) in visited:
        return

    visited.add(id(obj))
    if isinstance(obj, dict):
        entries = []
        for key, value in obj.items():
            if isinstance(value, type(target)) and target == value:
                entries.append((key, key, replacement))
            if isinstance(key, type(target)) and target == key:
                entries.append((key, replacement, obj[key]))

            replace_value(value, target, replacement, visited)
            replace_value(key, target, replacement, visited)
        for (prev_key, key, value) in entries:
            del obj[prev_key]
            obj[key] = value

    elif isinstance(obj, list):
        for index, item in enumerate(obj):
            if isinstance(item, type(target)) and target == item:
                obj[index] = replacement

            replace_value(item, target, replacement, visited)
    elif isinstance(obj, tuple):
        new_tuple = []
        for index, item in enumerate(obj):
            if isinstance(item, type(target)) and target == item:
                print('튜플이다 시발놈아')

                new_tuple.append(replacement)
            else:
                new_tuple.append(item)
            replace_value(item, target, replacement, visited)
        obj = tuple(new_tuple)
    elif isinstance(obj, set):
        new_set = set()
        for item in obj:
            if isinstance(item, type(target)) and target == item:
                new_set.add(target)
            else:
                new_set.add(item)
            replace_value(item, target, replacement, visited)
        obj.clear()
        obj.update(new_set)
    elif isinstance(obj, str):
        pass
    else:
        for attribute_name in dir(obj):
            if attribute_name.startswith('__') and attribute_name.endswith('__'):
                continue

            attribute_value = getattr(obj, attribute_name)
            if isinstance(attribute_value, type(target)) and target == attribute_value:
                try:
                    setattr(obj, attribute_name, replacement)
                except:
                    pass

            replace_value(attribute_value, target, replacement, visited)


def find_path(directory: str, extensions: list):
    for file in Path(directory).rglob('*'):
        if file.suffix.lower() in extensions:
            return file
    return None


def convert_jacket(in_path: str, out_path: str, music_id: str, skip_if_converted: bool = True):
    for sub_name in ['', '_s']:
        result_path = f'{out_path}/AssetBundleImages/jacket{sub_name}/ui_jacket_{music_id}{sub_name}.ab'
        if skip_if_converted and os.path.exists(result_path):
            continue

        if sub_name == '_s':
            new_m_path_id = int(music_id) + 10000000
            m_path_id_1 = -630615454984241609
            m_path_id_2 = -9068764124424944558
            cab_hash = '72f38b5f3114e28901b11d48eb6d85e6'
            new_cab_hash = f'{new_m_path_id}'
        else:
            new_m_path_id = int(music_id)
            m_path_id_1 = 739899962197238906
            m_path_id_2 = -1066836184272249663
            cab_hash = '86ca849a3b53af73406c67412dda69d5'
            new_cab_hash = f'{new_m_path_id}'

        env = UnityPy.load(f'./data/ui_jacket_001686{sub_name}.ab')
        for obj in env.objects:
            print(obj.type.name)

            tree = obj.read_typetree()
            recursive_string_replace(tree, '_001686', f'_{music_id}')

            # if obj.type.name == 'Sprite':
            #     tree['m_RenderDataKey']['first']['data[0]'] = new_m_path_id
            #     tree['m_RenderDataKey']['first']['data[1]'] = new_m_path_id
            #     tree['m_RenderDataKey']['first']['data[2]'] = new_m_path_id
            #     tree['m_RenderDataKey']['first']['data[3]'] = new_m_path_id
            #     tree['m_RD']['texture']['m_PathID'] = new_m_path_id

            # if obj.type.name == 'AssetBundle':
            #     tree['m_PreloadTable'][0]['m_PathID'] = -new_m_path_id
            #     tree['m_Container'][1][1]['asset']['m_PathID'] = -new_m_path_id
            #     tree['m_PreloadTable'][1]['m_PathID'] = new_m_path_id
            #     tree['m_Container'][0][1]['asset']['m_PathID'] = new_m_path_id

            if obj.type.name == 'Texture2D':
                tree['m_StreamData']['path'] = f'archive:/CAB-{new_cab_hash}/CAB-{new_cab_hash}.resS'

            obj.save_typetree(tree)

        # replace_value(env, m_path_id_1, new_m_path_id)
        # replace_value(env, m_path_id_2, -new_m_path_id)

        env.file.name = env.file.name.replace('_001686', f'_{music_id}')

        key = next(iter(env.file.container))
        env.file.container[key.replace('_001686', f'_{music_id}')] = env.file.container[key]
        del env.file.container[key]

        # CAB-##
        env.file.files[f'CAB-{new_cab_hash}'] = env.file.files[f'CAB-{cab_hash}']
        env.file.files[f'CAB-{new_cab_hash}'].assetbundle.m_Name = env.file.files[
            f'CAB-{new_cab_hash}'].assetbundle.m_Name.replace('_001686', f'_{music_id}')
        del env.file.files[f'CAB-{cab_hash}']

        env.file.files[f'CAB-{new_cab_hash}.resS'] = env.file.files[f'CAB-{cab_hash}.resS']
        del env.file.files[f'CAB-{cab_hash}.resS']

        os.makedirs(f'{out_path}/AssetBundleImages/jacket{sub_name}', exist_ok=True)

        with open(result_path, 'wb') as f:
            f.write(env.file.save())


def convert_movie(in_path: str, out_path: str, music_id: str, skip_if_converted: bool = True):
    """
    :param in_path: chart folder path
    :param out_path: output chart path
    :param music_id:
    :return:
    """

    movie_path = find_path(in_path, ['.mp4'])
    if movie_path is None:
        return

    result_path = f'{out_path}/MovieData/{music_id}.dat'
    if skip_if_converted and os.path.exists(result_path):
        return

    temp_ivf_path = f'{out_path}/tmp_{music_id}/{music_id}.ivf'

    stream = ffmpeg.input(movie_path)
    stream = ffmpeg.output(stream, temp_ivf_path, vcodec='vp9').overwrite_output()
    ffmpeg.run(stream)

    with patch.object(sys, 'argv', ['wannacri', 'createusm', temp_ivf_path, '--key', '0x7F4551499DF55E68']):
        create_usm()  # .ivf to .dat 파일 변환됨.

    os.makedirs(f'{out_path}/MovieData', exist_ok=True)
    shutil.move(f'{out_path}/tmp_{music_id}/{music_id}.dat', result_path)

    os.remove(temp_ivf_path)


def convert_music(in_path: str, out_path: str, music_id: str, skip_if_converted: bool = True):
    result_path_acb = f'{out_path}/SoundData/music{music_id}.acb'
    result_path_awb = f'{out_path}/SoundData/music{music_id}.awb'

    if skip_if_converted and os.path.exists(result_path_acb) and os.path.exists(result_path_awb):
        return

    shutil.copy('./data/music001686.acb', f'{out_path}/tmp_{music_id}/music.acb')
    shutil.copy('./data/music001686.awb', f'{out_path}/tmp_{music_id}/music.awb')

    music_path = find_path(in_path, ['.mp3'])
    stream = ffmpeg.input(music_path)
    stream = ffmpeg.output(stream, f'{out_path}/tmp_{music_id}/music.wav').overwrite_output()
    ffmpeg.run(stream)
    # automatically creates music folder
    os.system(
        f'.\\CriEncoder\\criatomencd.exe {out_path}/tmp_{music_id}/music.wav {out_path}/tmp_{music_id}/music/00000_streaming.hca -keycode=9170825592834449000')
    os.system(f'.\\SonicAudioTools\\AcbEditor.exe {out_path}/tmp_{music_id}/music')  # override .acb, .awb

    os.makedirs(f'{out_path}/SoundData', exist_ok=True)
    shutil.move(f'{out_path}/tmp_{music_id}/music.acb', result_path_acb)
    shutil.move(f'{out_path}/tmp_{music_id}/music.awb', result_path_awb)


def convert_chart_and_metadata(in_path: str, out_path: str, music_id: str, is_festival: bool = False, offset: int = 0):
    parser = Lark.open('./simai.lark', parser="lalr")
    metadata = SimaiTransformer().transform(parser.parse(open(f'{in_path}/maidata.txt', encoding='UTF8').read()))

    os.makedirs(f'{out_path}/music/music{music_id}', exist_ok=True)

    level_dict = {
        '1': 1, '2': 2,
        '3': 3, '4': 4,
        '5': 5, '6': 6,
        '7': 7, '7+': 8,
        '8': 9, '8+': 10,
        '9': 11, '9+': 12,
        '10': 13, '10+': 14,
        '11': 15, '11+': 16,
        '12': 17, '12+': 18,
        '13': 19, '13+': 20,
        '14': 21, '14+': 22,
        '15': 23, '15+': 24
    }
    levels = {}
    for data in metadata:
        if data['type'] == 'level':
            level_value = data['value'][1]
            if level_value not in level_dict:
                level_value = '15+'

            levels[data['value'][0] - 2] = level_value


    notes = []
    for i in range(6):
        if i not in levels:  # 채보 있는놈
            notes.append({
                'file': {'path': f'{music_id}_0{i}.ma2'},
                'level': '0',
                'levelDecimal': '0',
                'notesDesigner': {'id': '0', 'str': None},
                'notesType': '0',
                'musicLevelID': '0',
                'maxNotes': '0',
                'isEnable': 'false'
            })
        else:  # 채보 없는놈
            level = levels[i]

            leveldecimal = '0'
            if '+' in level:
                leveldecimal = '7'

            # 채보 변환 (result.ma2 생성)

            # subprocess.run(
            #     f'.\\MaichartConverter_Win1071\\MaichartConverter.exe CompileSimai -p {in_path}/maidata.txt -f {'Ma2_104' if is_festival else 'Ma2'} -o {out_path}/tmp_{music_id} -d {i + 2}',
            #     # ['.\\MaichartConverter_Win1071\\MaichartConverter.exe', 'CompileSimai', '-p', f'./{in_path}/maidata.txt', '-f', 'Ma2_104' if is_festival else 'Ma2', '-o', f'{out_path}/tmp_{music_id}', 'd', f'{i + 2}'],
            #     stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True
            # )
            os.system(
                f'.\\MaichartConverter_Win1071\\MaichartConverter.exe CompileSimai -p "{in_path}/maidata.txt" -f {'Ma2_104' if is_festival else 'Ma2'} -o {out_path}/tmp_{music_id} -d {i + 2}')

            # offset 미루는 부분
            with open(f'{out_path}/tmp_{music_id}/result.ma2', encoding='utf-8') as f:
                data = f.read()

            data = data.split('\n\n')
            new_chart = []
            for line in data[2].split('\n'):
                line = line.split('\t')
                total = int(line[1]) * 384 + int(line[2]) + offset
                line[1] = str(total // 384)
                line[2] = str(total % 384)
                new_chart.append('\t'.join(line))
            data[2] = '\n'.join(new_chart)
            data = '\n\n'.join(data)

            with open(f'{out_path}/music/music{music_id}/{music_id}_0{i}.ma2', 'w', encoding='utf-8') as f:
                f.write(data)

            # metadata 작성
            notes.append({
                'file': {'path': f'{music_id}_0{i}.ma2'},
                'level': level.replace('+', ''),
                'levelDecimal': leveldecimal,
                'notesDesigner': {'id': '0', 'str': 'NZN'},
                'notesType': '0',
                'musicLevelID': str(level_dict[level]),
                'maxNotes': '0',
                'isEnable': 'true'
            })

    # Music metadata
    title = None
    artist = None
    bpm = None
    for data in metadata:
        if data['type'] == 'artist':
            artist = data['value']
        if data['type'] == 'title':
            title = data['value']
        if data['type'] == 'wholebpm' and int(data['value']) > 10:  # 10 bpm은 넘길 거임.
            bpm = data['value']

    levels = {}
    for data in metadata:
        if data['type'] == 'level':
            levels[data['value'][0] - 2] = data['value'][1]

    musicxml = xmltodict.parse(open('./data/Music.xml', encoding='UTF8').read())

    musicxml['MusicData']['dataName'] = f'music{music_id}'
    musicxml['MusicData']['name'] = {'id': str(int(music_id)), 'str': title}
    musicxml['MusicData']['sortName'] = f'{music_id}MUSIC'
    musicxml['MusicData']['artistName'] = {'id': '754', 'str': artist}
    musicxml['MusicData']['genreName'] = {'id': '105', 'str': 'maimai'}
    musicxml['MusicData']['eventName']['id'] = '1'
    musicxml['MusicData']['eventName']['str'] = '無期限常時解放'
    musicxml['MusicData']['movieName']['id'] = music_id
    musicxml['MusicData']['movieName']['str'] = title
    musicxml['MusicData']['cueName']['id'] = music_id
    musicxml['MusicData']['cueName']['str'] = title
    musicxml['MusicData']['bpm'] = bpm
    musicxml['MusicData']['notesData']['Notes'] = notes

    musicxml = xmltodict.unparse(musicxml)
    tree = ElementTree.ElementTree(ElementTree.fromstring(musicxml))
    ElementTree.indent(tree, space="  ", level=0)
    with open(f'{out_path}/music/music{music_id}/Music.xml', 'wb') as file:
        tree.write(file, encoding='utf-8', xml_declaration=True)


def convert(in_path: str, out_path: str, music_id: str, skip_if_converted: bool = False):
    os.makedirs(f'{out_path}/tmp_{music_id}', exist_ok=True)
    convert_jacket(in_path, out_path, music_id, skip_if_converted=False)
    convert_movie(in_path, out_path, music_id, skip_if_converted)
    convert_music(in_path, out_path, music_id, skip_if_converted)
    convert_chart_and_metadata(in_path, out_path, music_id, is_festival=True, offset=0)
    shutil.rmtree(f'{out_path}/tmp_{music_id}', ignore_errors=True)


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    print('start')

    inputs_path = './inputs'
    out_path = './outputs'

    tasks = []
    music_id_numeric = 2000
    for name in os.listdir(inputs_path):
        in_path = f'{inputs_path}/{name}'
        if os.path.isdir(in_path):
            # {'in_path': in_path, 'out_path': out_path, 'music_id': '%06d' % music_id, 'skip_if_converted': True}
            music_id = '%06d' % music_id_numeric
            tasks.append((in_path, out_path, music_id, True))
            music_id_numeric += 1

    with ThreadPoolExecutor() as executor:
        results = []
        for result in executor.map(convert, *zip(*tasks)):
            results.append(result)
            print(f"Task completed. Progress: {len(results)}/{len(tasks)}")

    print('end')
