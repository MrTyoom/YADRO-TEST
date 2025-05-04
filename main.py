import json
import xml.etree.ElementTree as ET
import os

from typing import *



from collections import defaultdict

INDENT = '    '
INPUT_PATH = 'input'
OUTPUT_PATH = 'out'
OUTPUT_PATH.mkdir(exist_ok=True)

ClassInfo = Tuple[
    Dict[str, str],  # Атрибуты класса
    List[Dict[str, str]],  # Атрибуты-параметры
    List[str],  # Связанные классы
    Set[str]  # Множество значений
]
ClassDict = Dict[str, ClassInfo]



def automatic_build_xml(class_dict: ClassDict, root_class: str = "BTS") -> ET.Element:
    # Словарь созданных элементов
    created_elements = {}

    '''
    create_element - функция, которая рекурсивно строит дерево зависимостей
    (все классы, атрибуты, зависимости, значения), все записывается в словарь created_elements
    '''

    def create_element(class_name: str, parent: Optional[ET.Element] = None, level: int = 0) -> Optional[ET.Element]:
        if class_name in created_elements:
            return created_elements[class_name]

        class_info = class_dict.get(class_name)
        if not class_info:
            return None

        # Построение зависимостей, в зависимости от того, является ли элемент корнем
        if parent is None:
            element = ET.Element(class_name)
        else:
            element = ET.SubElement(parent, class_name)

        # Добавление атрибутов
        for attr in class_info[1]:
            attr_elem = ET.SubElement(element, attr['name'])
            attr_elem.text = attr['type']

        # Специальная конструкция, чтобы получались не самозакрывающиеся теги
        if not class_info[1] and not class_info[2]:
            element.text = '\n' + level * INDENT

        # Сохраняем созданный элемент
        created_elements[class_name] = element

        # Рекурсивно создаем связные элементы
        for related_class in class_info[2]:
            create_element(related_class, element, level + 1)

        return element

    root_element = create_element(root_class)

    return root_element


def create_class_dict(root: ET.Element) -> ClassDict:
    '''
    all_data_info = {
                'name' : [Class, [attribute1, attribute2, ...], [source1, source2, ...], {values}],
                ......
            }
    '''
    all_data_info = defaultdict(list)
    cur_name = ''

    for elem in root.iter():
        if elem.tag == 'Class':
            all_data_info[elem.attrib['name']].append(elem.attrib)  # Помещаем класс в словарь
            all_data_info[elem.attrib['name']].append([])  # Сразу создаем список для атрибутов
            all_data_info[elem.attrib['name']].append([])  # Сразу добавляем список для связей
            all_data_info[elem.attrib['name']].append(set())  # Сразу добавляем множество для значений параметров

            cur_name = elem.attrib['name']
        elif elem.tag == 'Attribute':
            all_data_info[cur_name][1].append(elem.attrib)
        elif elem.tag == 'Aggregation':
            all_data_info[elem.attrib['source']][-1].add(elem.attrib['sourceMultiplicity'])
            all_data_info[elem.attrib['target']][-1].add(elem.attrib['targetMultiplicity'])
            all_data_info[elem.attrib['target']][2].append(elem.attrib['source'])

    return all_data_info


def create_config(xml_file: str, filename: str) -> None:
    tree = ET.parse(xml_file)
    root = tree.getroot()

    class_dict = create_class_dict(root)
    structure_xml = automatic_build_xml(class_dict)

    new_tree = ET.ElementTree(structure_xml)
    ET.indent(new_tree, space='    ', level=0)
    new_tree.write(filename, encoding='utf-8', xml_declaration=True)

    meta_data(class_dict, 'meta.json')


def meta_data(class_dict: ClassDict, output_json: str) -> None:
    json_data = []
    for key in class_dict:
        cur_class = class_dict[key]

        min_max_value = cur_class[-1].pop().split('..')  # Извлечение минимального/максимального
                                                         # возможного принимаемого значения

        source_list_parameters = []                      # Вспомогательная структура для добавления в атрибуты
        for el in cur_class[-2]:
            source_list_parameters.append({
                'name': el,
                'type': 'class'
            })

        all_parameters = cur_class[1] + source_list_parameters

        if len(min_max_value) == 1:
            mn = mx = min_max_value[0]
        else:
            mn, mx = min_max_value

        json_data.append({
            'class': cur_class[0]['name'],
            'documentation': cur_class[0]['documentation'],
            'isRoot': cur_class[0]['isRoot'],
            'max': mx,
            'min': mn,
            'parameters': all_parameters
        })

        if json_data[-1]['isRoot'] == 'true':
            del json_data[-1]['max']
            del json_data[-1]['min']

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=4, ensure_ascii=False)


def delta_json(config_json: str,
               patched_config_json: str,
               output_json: str
               ) -> None:
    with open(config_json, 'r', encoding='utf-8') as config1:
        config_data = json.load(config1)

    with open(patched_config_json, 'r', encoding='utf-8') as config2:
        patched_config_data = json.load(config2)

    added = []
    consisted_params = []
    deletions = []
    updated_params = []
    updates = []

    for el in config_data:
        try:
            tmp_res = patched_config_data[el]

            if tmp_res != config_data[el]:
                updates.append({'key': el, 'from': config_data[el], 'to': tmp_res})
                updated_params.append(el)
            else:
                consisted_params.append(el)

        except KeyError:
            deletions.append(el)

    for el in patched_config_data:
        if el not in deletions and el not in updated_params and el not in consisted_params:
            added.append({'key': el, 'value': patched_config_data[el]})

    json_data = {
        'additions': added,
        'deletions': deletions,
        'updates': updates
    }

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=4, ensure_ascii=False)


def res_patched_json(config_json: str,
                     delta_json: str,
                     output_json: str
                     ) -> None:
    with open(config_json, 'r', encoding='utf-8') as config:
        config_data = json.load(config)

    with open(delta_json, 'r', encoding='utf-8') as delta:
        delta_data = json.load(delta)

    merged_delta_elements = delta_data['updates'] + delta_data['additions']
    res_patched_config = {}
    for el in merged_delta_elements:
        try:
            res_patched_config[el['key']] = el['to']
        except KeyError:
            res_patched_config[el['key']] = el['value']

    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(res_patched_config, f, indent=4, ensure_ascii=False)


if __name__ == "__main__":
    create_config(INPUT_PATH + '/impulse_test_input.xml',
                  OUTPUT_PATH + '/config.xml')
    delta_json(INPUT_PATH + '/config.json',
               INPUT_PATH + '/patched_config.json',
               OUTPUT_PATH + '/delta.json')
    res_patched_json(INPUT_PATH + '/config.json',
                     OUTPUT_PATH + '/delta.json',
                     OUTPUT_PATH + '/res_patched_config.json')
