'''
What a directory holding a project is named by.

A recipe standing in for a project is read the same way.
'''

import os

# Tried in this order, which is the order `Context.load_project` reads them in.
PROJECT_FILE_NAMES = ('golemfile.py', 'golemfile.json')

PROJECT_FILE_NAMES_LISTED = ' or '.join(
    "'{}'".format(name) for name in PROJECT_FILE_NAMES
)


def holds_a_project(directory: str) -> bool:
    '''Is there anything in directory Golem can load a project from?'''
    return any(
        os.path.exists(os.path.join(directory, name)) for name in PROJECT_FILE_NAMES
    )
