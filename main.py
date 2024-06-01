import shutil
import os
import sys
import ffmpeg
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
import pandas as pd


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


def find_path(directory: str, extensions: list):
    for file in Path(directory).rglob('*'):
        if file.suffix.lower() in extensions:
            return file
    return None


def get_or_new_id(cache_path: str, name: str, initial_value: int):
    if not os.path.exists(cache_path):
        new_id = initial_value
        df = pd.DataFrame({'id': [new_id], 'name': [name]})
        df.to_csv(cache_path, index=False, sep='\t')
        return new_id

    df = pd.read_csv(cache_path, sep='\t')
    tmp_df = df[df['name'] == name]
    if len(tmp_df) > 0:
        return tmp_df['id'].iloc[0]

    new_id = int(df['id'].max()) + 1
    df = pd.concat([df, pd.DataFrame({'id': [new_id], 'name': [name]})])
    df.to_csv(cache_path, index=False, sep='\t')
    return new_id


class Chart:
    in_path: str
    out_path: str

    music_id: str

    temp_path: str
    maidata_path: str

    def __init__(self, inputs_path: str, in_path: str, out_path: str):
        if not os.path.exists(f'{in_path}/maidata.txt'):
            raise FileNotFoundError(f'{in_path}/maidata.txt')

        self.in_path = in_path
        self.out_path = out_path

        self.music_id = '%06d' % get_or_new_id(f'{inputs_path}/music_id.tsv', in_path, 2001)

        self.temp_path = f'{out_path}/tmp_{self.music_id}'
        self.maidata_path = f'{out_path}/maidata.txt'


def read_charts(inputs_path: str, out_path: str) -> list:
    charts = []

    for folder_name in os.listdir(inputs_path):
        if not os.path.isdir(f'{inputs_path}/{folder_name}'):
            continue

        if os.path.exists(f'{inputs_path}/{folder_name}/maidata.txt'):
            # it is chart
            in_path = f'{inputs_path}/{folder_name}'
            charts.append(Chart(inputs_path, in_path, out_path))
            continue

    return charts


def convert_jacket(chart: Chart, skip_if_converted: bool = True):
    for sub_name in ['', '_s']:
        result_path = f'{chart.out_path}/AssetBundleImages/jacket{sub_name}/ui_jacket_{chart.music_id}{sub_name}.ab'
        if skip_if_converted and os.path.exists(result_path):
            continue

        if sub_name == '_s':
            cab_hash = '72f38b5f3114e28901b11d48eb6d85e6'
            new_cab_hash = f'{int(chart.music_id) + 10000000}'
        else:
            cab_hash = '86ca849a3b53af73406c67412dda69d5'
            new_cab_hash = f'{int(chart.music_id)}'

        env = UnityPy.load(f'./data/ui_jacket_001686{sub_name}.ab')

        # modify unity asset metadata
        for obj in env.objects:
            tree = obj.read_typetree()
            recursive_string_replace(tree, '_001686', f'_{chart.music_id}')

            if obj.type.name == 'Texture2D':
                tree['m_StreamData']['path'] = f'archive:/CAB-{new_cab_hash}/CAB-{new_cab_hash}.resS'

            obj.save_typetree(tree)

        env.file.name = env.file.name.replace('_001686', f'_{chart.music_id}')

        key = next(iter(env.file.container))
        env.file.container[key.replace('_001686', f'_{chart.music_id}')] = env.file.container[key]
        del env.file.container[key]

        # CAB-##
        env.file.files[f'CAB-{new_cab_hash}'] = env.file.files[f'CAB-{cab_hash}']
        env.file.files[f'CAB-{new_cab_hash}'].assetbundle.m_Name = env.file.files[
            f'CAB-{new_cab_hash}'].assetbundle.m_Name.replace('_001686', f'_{chart.music_id}')
        del env.file.files[f'CAB-{cab_hash}']

        env.file.files[f'CAB-{new_cab_hash}.resS'] = env.file.files[f'CAB-{cab_hash}.resS']
        del env.file.files[f'CAB-{cab_hash}.resS']

        # save temp
        temp_ab_path = f'{chart.temp_path}/{chart.music_id}{sub_name}.ab'
        with open(temp_ab_path, 'wb') as f:
            f.write(env.file.save())

        env = UnityPy.load(temp_ab_path)
        # edit image
        for obj in env.objects:
            if obj.type.name == 'Texture2D':
                data = obj.read()
                image_path = find_path(chart.in_path, ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.svg'])
                data.image = Image.open(image_path).resize(data.image.size).convert('RGB').convert('RGBA')
                data.save()

        # save
        os.makedirs(f'{chart.out_path}/AssetBundleImages/jacket{sub_name}', exist_ok=True)

        with open(result_path, 'wb') as f:
            f.write(env.file.save())


def convert_movie(chart: Chart, skip_if_converted: bool = True):

    result_path = f'{chart.out_path}/MovieData/{chart.music_id}.dat'
    if skip_if_converted and os.path.exists(result_path):
        return

    movie_path = find_path(chart.in_path, ['.mp4'])
    if movie_path is not None:
        probe = ffmpeg.probe(movie_path)
        stream = ffmpeg.input(movie_path)
    else:
        image_path = find_path(chart.in_path, ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.svg'])
        probe = ffmpeg.probe(image_path)
        stream = ffmpeg.input(image_path, loop=1, t=10 / 30, framerate=30)

    video_info = next(stream for stream in probe['streams'] if stream['codec_type'] == 'video')
    width = int(video_info['width'])
    height = int(video_info['height'])

    # 1:1 비율로 중앙 크롭할 크기 계산
    crop_size = min(width, height)
    x_offset = (width - crop_size) // 2
    y_offset = (height - crop_size) // 2

    temp_ivf_path = f'{chart.temp_path}/{chart.music_id}.ivf'
    (stream
     .filter('crop', crop_size, crop_size, x_offset, y_offset)
     .filter('scale', 1080, 1080)
     .output(temp_ivf_path, vcodec='vp9', r=30).overwrite_output().run())

    with patch.object(sys, 'argv', ['wannacri', 'createusm', temp_ivf_path, '--key', '0x7F4551499DF55E68']):
        create_usm()  # .ivf to .dat 파일 변환됨.

    os.makedirs(f'{chart.out_path}/MovieData', exist_ok=True)
    shutil.move(f'{chart.temp_path}/{chart.music_id}.dat', result_path)

    os.remove(temp_ivf_path)


def convert_music(chart: Chart, skip_if_converted: bool = True):
    result_path_acb = f'{chart.out_path}/SoundData/music{chart.music_id}.acb'
    result_path_awb = f'{chart.out_path}/SoundData/music{chart.music_id}.awb'

    if skip_if_converted and os.path.exists(result_path_acb) and os.path.exists(result_path_awb):
        return

    shutil.copy('./data/music001686.acb', f'{chart.temp_path}/music.acb')
    shutil.copy('./data/music001686.awb', f'{chart.temp_path}/music.awb')

    music_path = find_path(chart.in_path, ['.mp3'])
    stream = ffmpeg.input(music_path)
    stream = ffmpeg.output(stream, f'{chart.temp_path}/music.wav').overwrite_output()
    ffmpeg.run(stream)
    # automatically creates music folder
    os.system(
        f'.\\CriEncoder\\criatomencd.exe '
        f'{chart.temp_path}/music.wav {chart.temp_path}/music/00000_streaming.hca '
        f'-keycode=9170825592834449000'
    )
    os.system(f'.\\SonicAudioTools\\AcbEditor.exe {chart.temp_path}/music')  # override .acb, .awb

    os.makedirs(f'{chart.out_path}/SoundData', exist_ok=True)
    shutil.move(f'{chart.temp_path}/music.acb', result_path_acb)
    shutil.move(f'{chart.temp_path}/music.awb', result_path_awb)


def convert_chart_and_metadata(chart: Chart, is_festival: bool = False, offset: int = 0):
    parser = Lark.open('./simai.lark', parser="lalr")
    metadata = SimaiTransformer().transform(parser.parse(open(f'{chart.in_path}/maidata.txt', encoding='UTF8').read()))

    os.makedirs(f'{chart.out_path}/music/music{chart.music_id}', exist_ok=True)

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
                'file': {'path': f'{chart.music_id}_0{i}.ma2'},
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
            chart_type = 'Ma2_104' if is_festival else 'Ma2'
            os.system(
                f'.\\MaichartConverter_Win1071\\MaichartConverter.exe CompileSimai '
                f'-p "{chart.in_path}/maidata.txt" '
                f'-f {chart_type} '
                f'-o {chart.temp_path} '
                f'-d {i + 2} '
            )

            # offset 미루는 부분
            with open(f'{chart.temp_path}/result.ma2', encoding='utf-8') as f:
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

            with open(f'{chart.out_path}/music/music{chart.music_id}/{chart.music_id}_0{i}.ma2', 'w', encoding='utf-8') as f:
                f.write(data)

            # metadata 작성
            notes.append({
                'file': {'path': f'{chart.music_id}_0{i}.ma2'},
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
    chart_first_bpm = None
    for data in metadata:
        if data['type'] == 'artist':
            artist = data['value']
        if data['type'] == 'title':
            title = data['value']
        if data['type'] == 'wholebpm' and int(data['value']) > 10:  # 10 bpm은 넘길 거임.
            bpm = data['value']
        if data['type'] == 'chart':
            chart_first_bpm = data['value'][1].split('(')[1].split(')')[0]

    if bpm is None:
        bpm = chart_first_bpm
    if bpm is None:
        bpm = 0

    levels = {}
    for data in metadata:
        if data['type'] == 'level':
            levels[data['value'][0] - 2] = data['value'][1]

    musicxml = xmltodict.parse(open('./data/Music.xml', encoding='UTF8').read())

    musicxml['MusicData']['dataName'] = f'music{chart.music_id}'
    musicxml['MusicData']['name'] = {'id': str(int(chart.music_id)), 'str': title}
    musicxml['MusicData']['sortName'] = f'{chart.music_id}MUSIC'
    musicxml['MusicData']['artistName'] = {'id': '754', 'str': artist}
    musicxml['MusicData']['genreName'] = {'id': '105', 'str': 'maimai'}
    musicxml['MusicData']['eventName']['id'] = '1'
    musicxml['MusicData']['eventName']['str'] = '無期限常時解放'
    musicxml['MusicData']['movieName']['id'] = chart.music_id
    musicxml['MusicData']['movieName']['str'] = title
    musicxml['MusicData']['cueName']['id'] = chart.music_id
    musicxml['MusicData']['cueName']['str'] = title
    musicxml['MusicData']['bpm'] = bpm
    musicxml['MusicData']['notesData']['Notes'] = notes

    musicxml = xmltodict.unparse(musicxml)
    tree = ElementTree.ElementTree(ElementTree.fromstring(musicxml))
    ElementTree.indent(tree, space="  ", level=0)
    with open(f'{chart.out_path}/music/music{chart.music_id}/Music.xml', 'wb') as file:
        tree.write(file, encoding='utf-8', xml_declaration=True)


def convert(chart: Chart):
    os.makedirs(chart.temp_path, exist_ok=True)
    convert_jacket(chart, skip_if_converted=True)
    convert_movie(chart, skip_if_converted=True)
    convert_music(chart, skip_if_converted=True)
    convert_chart_and_metadata(chart, is_festival=True, offset=0)
    shutil.rmtree(chart.temp_path, ignore_errors=True)


def add_asset_bundle_dependencies(out_path: str, music_ids: list):
    env = UnityPy.load(f'./data/AssetBundleImages')
    for obj in env.objects:
        if obj.type.name == 'AssetBundleManifest':
            tree = obj.read_typetree()

            while len(tree['AssetBundleNames']) < len(tree['AssetBundleInfos']):
                tree['AssetBundleNames'].append(tree['AssetBundleNames'][0])

            while len(tree['AssetBundleInfos']) < len(tree['AssetBundleNames']):
                tree['AssetBundleInfos'].append(tree['AssetBundleInfos'][0])

            for music_id in music_ids:
                tree['AssetBundleNames'].append((len(tree['AssetBundleNames']), f'jacket/ui_jacket_{music_id}.ab'))
                tree['AssetBundleInfos'].append((len(tree['AssetBundleInfos']), {
                    'AssetBundleHash': {
                        'bytes[0]': 0, 'bytes[1]': 0, 'bytes[2]': 0, 'bytes[3]': 0, 'bytes[4]': 0, 'bytes[5]': 0,
                        'bytes[6]': 0, 'bytes[7]': 0, 'bytes[8]': 0,
                        'bytes[9]': 0, 'bytes[10]': 0, 'bytes[11]': 0, 'bytes[12]': 0, 'bytes[13]': 0, 'bytes[14]': 0,
                        'bytes[15]': 0
                    },
                    'AssetBundleDependencies': []
                }))
                tree['AssetBundleNames'].append((len(tree['AssetBundleNames']), f'jacket_s/ui_jacket_{music_id}_s.ab'))
                tree['AssetBundleInfos'].append((len(tree['AssetBundleInfos']), {
                    'AssetBundleHash': {
                        'bytes[0]': 0, 'bytes[1]': 0, 'bytes[2]': 0, 'bytes[3]': 0, 'bytes[4]': 0, 'bytes[5]': 0,
                        'bytes[6]': 0, 'bytes[7]': 0, 'bytes[8]': 0,
                        'bytes[9]': 0, 'bytes[10]': 0, 'bytes[11]': 0, 'bytes[12]': 0, 'bytes[13]': 0, 'bytes[14]': 0,
                        'bytes[15]': 0
                    },
                    'AssetBundleDependencies': []
                }))

            obj.save_typetree(tree)

    os.makedirs(f'{out_path}/AssetBundleImages')
    with open(f'{out_path}/AssetBundleImages/AssetBundleImages', 'wb') as f:
        f.write(env.file.save())


if __name__ == '__main__':
    print('start')

    param_inputs_path = './inputs'
    param_out_path = './outputs'

    charts = read_charts(param_inputs_path, param_out_path)

    add_asset_bundle_dependencies(param_out_path, [chart.music_id for chart in charts])
    with ThreadPoolExecutor() as executor:
        results = []
        for result in executor.map(convert, charts):
            results.append(result)
            print(f"Task completed. Progress: {len(results)}/{len(charts)}")

    print('end')
