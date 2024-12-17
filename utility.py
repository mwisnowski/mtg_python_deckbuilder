def pluralize(word):
    if word.endswith('y'):
        return word[:-1] + 'ies'
    elif word.endswith(('s', 'sh', 'ch', 'x', 'z')):
        return word + 'es'
    elif word.endswith(('f')):
        return word[:-1] + 'ves'
    else:
        return word + 's'

def sort_list(list_to_sort):
    if isinstance(list_to_sort, list):
        list_to_sort = sorted(list_to_sort)
        return list_to_sort
    else:
        return list_to_sort
  