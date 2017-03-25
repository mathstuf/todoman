import datetime
from os.path import isdir
from unittest.mock import patch

import hypothesis.strategies as st
import pytest
from dateutil.tz import tzlocal
from freezegun import freeze_time
from hypothesis import given

from todoman.cli import cli
from todoman.model import Database, Todo

# TODO: test --grep


def test_list(tmpdir, runner, create):
    result = runner.invoke(cli, ['list'], catch_exceptions=False)
    assert not result.exception
    assert not result.output.strip()

    create(
        'test.ics',
        'SUMMARY:harhar\n'
    )
    result = runner.invoke(cli, ['list'])
    assert not result.exception
    assert 'harhar' in result.output


def test_no_default_list(runner):
    result = runner.invoke(cli, ['new', 'Configure a default list'])

    assert result.exception
    assert ('Error: Invalid value for "--list" / "-l": You must set '
            '"default_list" or use -l.' in result.output)


def test_no_extra_whitespace(tmpdir, runner, create):
    """
    Test that we don't output extra whitespace

    Test that we don't output a lot of extra whitespace when there are no
    tasks, or when there are tasks (eg: both scenarios).

    Note: Other tests should be set up so that comparisons don't care much
    about whitespace, so that if this changes, only this test should fail.
    """
    result = runner.invoke(cli, ['list'], catch_exceptions=False)
    assert not result.exception
    assert result.output == '\n'

    create(
        'test.ics',
        'SUMMARY:harhar\n'
    )
    result = runner.invoke(cli, ['list'])
    assert not result.exception
    assert len(result.output.splitlines()) == 1


def test_percent(tmpdir, runner, create):
    create(
        'test.ics',
        'SUMMARY:harhar\n'
        'PERCENT-COMPLETE:78\n'
    )
    result = runner.invoke(cli, ['list'])
    assert not result.exception
    assert '78%' in result.output


def test_list_inexistant(tmpdir, runner, create):
    result = runner.invoke(cli, ['list', 'nonexistant'])
    assert result.exception
    assert 'Error: Invalid value for "lists":' in result.output


def test_show_existing(tmpdir, runner, create):
    create(
        'test.ics',
        'SUMMARY:harhar\n'
        'DESCRIPTION:Lots of text. Yum!\n'
    )
    result = runner.invoke(cli, ['list'])
    result = runner.invoke(cli, ['show', '1'])
    assert not result.exception
    assert 'harhar' in result.output
    assert 'Lots of text. Yum!' in result.output


def test_show_inexistant(tmpdir, runner, create):
    create(
        'test.ics',
        'SUMMARY:harhar\n'
    )
    result = runner.invoke(cli, ['list'])
    result = runner.invoke(cli, ['show', '2'])
    assert result.exit_code == -2
    assert result.output == 'No todo with id 2.\n'


def test_human(runner):
    result = runner.invoke(cli, [
        'new', '-l', 'default', '-d', 'tomorrow', 'hail belzebub'
    ])
    assert not result.exception
    assert 'belzebub' in result.output

    result = runner.invoke(cli, ['list'])
    assert not result.exception
    assert 'belzebub' in result.output


@pytest.mark.xfail(reason='issue#9')
def test_two_events(tmpdir, runner):
    tmpdir.join('default/test.ics').write(
        'BEGIN:VCALENDAR\n'
        'BEGIN:VTODO\n'
        'SUMMARY:task one\n'
        'END:VTODO\n'
        'BEGIN:VTODO\n'
        'SUMMARY:task two\n'
        'END:VTODO\n'
        'END:VCALENDAR'
    )
    result = runner.invoke(cli, ['list'])
    assert not result.exception
    assert len(result.output.splitlines()) == 2
    assert 'task one' in result.output
    assert 'task two' in result.output


def test_default_command(tmpdir, runner, create):
    create(
        'test.ics',
        'SUMMARY:harhar\n'
    )
    result = runner.invoke(cli)
    assert not result.exception
    assert 'harhar' in result.output


def test_delete(runner, create):
    create(
        'test.ics',
        'SUMMARY:harhar\n'
    )
    result = runner.invoke(cli, ['list'])
    assert not result.exception
    result = runner.invoke(cli, ['delete', '1', '--yes'])
    assert not result.exception
    result = runner.invoke(cli, ['list'])
    assert not result.exception
    assert not result.output.strip()


def test_delete_prompt(todo_factory, runner, default_database):
    todo_factory()

    result = runner.invoke(cli, ['delete', '1'], input='yes')

    assert not result.exception
    assert '[y/N]: yes\nDeleting "YARR!"' in result.output

    default_database.update_cache()
    assert len(list(default_database.todos())) == 0


def test_copy(tmpdir, runner, create):
    tmpdir.mkdir('other_list')
    create(
        'test.ics',
        'SUMMARY:test_copy\n'
    )
    result = runner.invoke(cli, ['list'])
    assert not result.exception
    assert 'test_copy' in result.output
    assert 'default' in result.output
    assert 'other_list' not in result.output
    result = runner.invoke(cli, ['copy', '-l', 'other_list', '1'])
    assert not result.exception
    result = runner.invoke(cli, ['list'])
    assert not result.exception
    assert 'test_copy' in result.output
    assert 'default' in result.output
    assert 'other_list' in result.output


def test_move(tmpdir, runner, create):
    tmpdir.mkdir('other_list')
    create(
        'test.ics',
        'SUMMARY:test_move\n'
    )
    result = runner.invoke(cli, ['list'])
    assert not result.exception
    assert 'test_move' in result.output
    assert 'default' in result.output
    assert 'other_list' not in result.output
    result = runner.invoke(cli, ['move', '-l', 'other_list', '1'])
    assert not result.exception
    result = runner.invoke(cli, ['list'])
    assert not result.exception
    assert 'test_move' in result.output
    assert 'default' not in result.output
    assert 'other_list' in result.output


@freeze_time('2017-03-17 20:22:19')
def test_dtstamp(tmpdir, runner, create):
    """Test that we add the DTSTAMP to new entries as per RFC5545."""
    result = runner.invoke(cli, ['new', '-l', 'default', 'test event'])
    assert not result.exception

    db = Database([tmpdir.join('default')],
                  tmpdir.join('/dtstamp_cache'))
    todo = list(db.todos())[0]
    assert todo.dtstamp is not None
    assert todo.dtstamp == datetime.datetime.now(tz=tzlocal())


def test_default_list(tmpdir, runner, create):
    """Test the default_list config parameter"""
    result = runner.invoke(cli, ['new', 'test default list'])
    assert result.exception

    path = tmpdir.join('config')
    path.write('default_list = default\n', 'a')

    result = runner.invoke(cli, ['new', 'test default list'])
    assert not result.exception

    db = Database([tmpdir.join('default')],
                  tmpdir.join('/default_list'))
    todo = list(db.todos())[0]
    assert todo.summary == 'test default list'


@pytest.mark.parametrize(
    'default_due, expected_due_hours', [(None, 24), (1, 1), (0, None)],
    ids=['not specified', 'greater than 0', '0']
)
def test_default_due(
    tmpdir, runner, create, default_due, expected_due_hours
):
    """Test setting the due date using the default_due config parameter"""
    if default_due is not None:
        path = tmpdir.join('config')
        path.write('default_due = {}\n'.format(default_due), 'a')

    runner.invoke(cli, ['new', '-l', 'default', 'aaa'])
    db = Database([tmpdir.join('default')], tmpdir.join('/default_list'))
    todo = list(db.todos())[0]

    if expected_due_hours is None:
        assert todo.due is None
    else:
        assert (todo.due - todo.created_at) == datetime.timedelta(
            hours=expected_due_hours
        )


@freeze_time(datetime.datetime.now())
def test_default_due2(tmpdir, runner, create, default_database):
    cfg = tmpdir.join('config')
    cfg.write('default_due = 24\n', 'a')

    r = runner.invoke(cli, ['new', '-ldefault', '-dtomorrow', 'aaa'])
    assert not r.exception
    r = runner.invoke(cli, ['new', '-ldefault', 'bbb'])
    assert not r.exception
    r = runner.invoke(cli, ['new', '-ldefault', '-d', 'one hour', 'ccc'])
    assert not r.exception

    default_database.update_cache()
    todos = {t.summary: t for t in default_database.todos(all=True)}
    assert todos['aaa'].due.date() == todos['bbb'].due.date()
    assert todos['ccc'].due == todos['bbb'].due - datetime.timedelta(hours=23)


def test_sorting_fields(tmpdir, runner, default_database):
    tasks = []
    for i in range(1, 10):
        days = datetime.timedelta(days=i)

        todo = Todo(new=True)
        todo.list = next(default_database.lists())
        todo.due = datetime.datetime.now() + days
        todo.created_at = datetime.datetime.now() - days
        todo.summary = 'harhar{}'.format(i)
        tasks.append(todo)

        default_database.save(todo)

    fields = (
        'id',
        'uid',
        'summary',
        'due',
        'priority',
        'created_at',
        'completed_at',
        'dtstamp',
        'status',
        'description',
        'location',
        'categories',
    )

    @given(sort_key=st.lists(
        st.sampled_from(fields + tuple('-' + x for x in fields)),
        unique=True
    ))
    def run_test(sort_key):
        sort_key = ','.join(sort_key)
        result = runner.invoke(cli, ['list', '--sort', sort_key])
        assert not result.exception
        assert result.exit_code == 0
        assert len(result.output.strip().splitlines()) == len(tasks)

    run_test()


def test_sorting_output(tmpdir, runner, create):
    create(
        'test.ics',
        'SUMMARY:aaa\n'
        'DUE;VALUE=DATE-TIME;TZID=ART:20160102T000000\n'
    )
    create(
        'test2.ics',
        'SUMMARY:bbb\n'
        'DUE;VALUE=DATE-TIME;TZID=ART:20160101T000000\n'
    )

    examples = [
        ('-summary', ['aaa', 'bbb']),
        ('due', ['aaa', 'bbb'])
    ]

    # Normal sorting, reversed by default
    all_examples = [(['--sort', key], order) for key, order in examples]

    # Testing --reverse, same exact output
    all_examples.extend((['--reverse', '--sort', key], order)
                        for key, order in examples)

    # Testing --no-reverse
    all_examples.extend((['--no-reverse', '--sort', key], reversed(order))
                        for key, order in examples)

    for args, order in all_examples:
        result = runner.invoke(cli, ['list'] + args)
        assert not result.exception
        lines = result.output.splitlines()
        for i, task in enumerate(order):
            assert task in lines[i]


def test_sorting_null_values(tmpdir, runner, create):
    create(
        'test.ics',
        'SUMMARY:aaa\n'
        'PRIORITY:9\n'
    )
    create(
        'test2.ics',
        'SUMMARY:bbb\n'
        'DUE;VALUE=DATE-TIME;TZID=ART:20160101T000000\n'
    )

    result = runner.invoke(cli)
    assert not result.exception
    assert 'bbb' in result.output.splitlines()[0]
    assert 'aaa' in result.output.splitlines()[1]


def test_sort_invalid_fields(runner):
    result = runner.invoke(cli, ['list', '--sort', 'hats'])

    assert result.exception
    assert 'Invalid value for "--sort": Unknown field "hats"' in result.output


@pytest.mark.parametrize('hours', [72, -72])
def test_color_due_dates(tmpdir, runner, create, hours):
    due = datetime.datetime.now() + datetime.timedelta(hours=hours)
    create(
        'test.ics',
        'SUMMARY:aaa\n'
        'STATUS:IN-PROGRESS\n'
        'DUE;VALUE=DATE-TIME;TZID=ART:{}\n'
        .format(due.strftime('%Y%m%dT%H%M%S'))
    )

    result = runner.invoke(cli, ['--color', 'always'])
    assert not result.exception
    due_str = due.strftime('%Y-%m-%d')
    if hours == 72:
        assert result.output == \
            '1  [ ]    {}  aaa @default\x1b[0m\n'.format(due_str)
    else:
        assert result.output == \
            '1  [ ]    \x1b[31m{}\x1b[0m  aaa @default\x1b[0m\n' \
            .format(due_str)


def test_color_flag(runner, todo_factory):
    todo_factory(due=datetime.datetime(2007, 3, 22))

    result = runner.invoke(cli, ['--color', 'always'], color=True)
    assert(
        result.output.strip() ==
        '1  [ ]    \x1b[31m2007-03-22\x1b[0m  YARR! @default\x1b[0m'
    )
    result = runner.invoke(cli, color=True)
    assert(
        result.output.strip() ==
        '1  [ ]    \x1b[31m2007-03-22\x1b[0m  YARR! @default\x1b[0m'
    )

    result = runner.invoke(cli, ['--color', 'never'], color=True)
    assert(
        result.output.strip() ==
        '1  [ ]    2007-03-22  YARR! @default'
    )


def test_flush(tmpdir, runner, create):
    create(
        'test.ics',
        'SUMMARY:aaa\n'
        'STATUS:COMPLETED\n'
    )

    result = runner.invoke(cli, ['list'])
    assert not result.exception

    create(
        'test2.ics',
        'SUMMARY:bbb\n'
    )

    result = runner.invoke(cli, ['list'])
    assert not result.exception
    assert '2  [ ]      bbb @default' in result.output

    result = runner.invoke(cli, ['flush'], input='y\n', catch_exceptions=False)
    assert not result.exception

    create(
        'test2.ics',
        'SUMMARY:bbb\n'
    )

    result = runner.invoke(cli, ['list'])
    assert not result.exception
    assert '1  [ ]      bbb @default' in result.output


def test_edit(runner, default_database):
    todo = Todo(new=True)
    todo.list = next(default_database.lists())
    todo.summary = 'Eat paint'
    todo.due = datetime.datetime(2016, 10, 3)
    default_database.save(todo)

    result = runner.invoke(cli, ['edit', '1', '--due', '2017-02-01'])
    assert not result.exception
    assert '2017-02-01' in result.output

    default_database.update_cache()
    todo = next(default_database.todos(all=True))
    assert todo.due == datetime.datetime(2017, 2, 1, tzinfo=tzlocal())
    assert todo.summary == 'Eat paint'


def test_edit_move(runner, todo_factory, default_database, tmpdir):
    """
    Test that editing the list in the UI edits the todo as expected

    The goal of this test is not to test the editor itself, but rather the
    `edit` command and its slightly-complex moving logic.
    """
    tmpdir.mkdir('another_list')

    default_database.paths = [
        str(tmpdir.join('default')),
        str(tmpdir.join('another_list')),
    ]
    default_database.update_cache()

    todo_factory(summary='Eat some headphones')

    lists = list(default_database.lists())
    another_list = next(filter(lambda x: x.name == 'another_list', lists))

    def moving_edit(self):
        self.current_list = another_list
        self._save_inner()

    with patch('todoman.interactive.TodoEditor.edit', moving_edit):
        result = runner.invoke(cli, ['edit', '1'])

    assert not result.exception

    default_database.update_cache()
    todos = list(default_database.todos())
    assert len(todos) == 1
    assert todos[0].list.name == 'another_list'


def test_empty_list(tmpdir, runner, create):
    for item in tmpdir.listdir():
        if isdir(str(item)):
            item.remove()

    result = runner.invoke(cli)
    expected = ("No lists found matching {}/*, create"
                " a directory for a new list").format(tmpdir)

    assert expected in result.output


def test_show_location(tmpdir, runner, create):
    create(
        'test.ics',
        'SUMMARY:harhar\n'
        'LOCATION:Boston\n'
    )

    result = runner.invoke(cli, ['show', '1'])
    assert 'Boston' in result.output


def test_location(runner):
    result = runner.invoke(cli, [
        'new', '-l', 'default', '--location', 'Chembur', 'Event Test'
    ])

    assert 'Chembur' in result.output


def test_sort_mixed_timezones(runner, create):
    """
    Test sorting mixed timezones.

    The times on this tests are carefully chosen so that a TZ-naive comparison
    gives the opposite results.
    """
    create(
        'test.ics',
        'SUMMARY:first\n'
        'DUE;VALUE=DATE-TIME;TZID=CET:20170304T180000\n'  # 1700 UTC
    )
    create(
        'test2.ics',
        'SUMMARY:second\n'
        'DUE;VALUE=DATE-TIME;TZID=HST:20170304T080000\n'  # 1800 UTC
    )

    result = runner.invoke(cli, ['list', '--all'])
    assert not result.exception
    output = result.output.strip()
    assert len(output.splitlines()) == 2
    assert 'second' in result.output.splitlines()[0]
    assert 'first' in result.output.splitlines()[1]


def test_humanize_interactive(runner):
    result = runner.invoke(cli, ['--humanize', '--porcelain', 'list'])

    assert result.exception
    assert result.output.strip() == \
        "Error: --porcelain and --humanize cannot be used at the same time."


def test_due_bad_date(runner):
    result = runner.invoke(cli, ['new', '--due', 'Not a date', 'Blargh!'])

    assert result.exception
    assert (
        'Error: Invalid value for "--due" / "-d": Time description not '
        'recognized: Not a date' == result.output.strip().splitlines()[-1]
    )


def test_multiple_todos_in_file(runner, create):
    create(
        'test.ics',
        'SUMMARY:a\n'
        'END:VTODO\n'
        'BEGIN:VTODO\n'
        'SUMMARY:b\n'
    )

    for _ in range(2):
        result = runner.invoke(cli, ['list'])
        assert ' a ' in result.output
        assert ' b ' in result.output
        assert 'warning: Todo is in read-only mode' in result.output

    result = runner.invoke(cli, ['done', '1'])
    assert result.exception
    assert 'Todo is in read-only mode because there are multiple todos' \
        in result.output

    result = runner.invoke(cli, ['show', '1'])
    assert not result.exception
    result = runner.invoke(cli, ['show', '2'])
    assert not result.exception


def test_todo_new(runner, default_database):
    # This isn't a very thurough test, but at least catches obvious regressions
    # like startup crashes or typos.

    with patch('urwid.MainLoop'):
        result = runner.invoke(cli, ['new', '-l', 'default'])

    # No SUMMARY error after UI runs
    assert isinstance(result.exception, SystemExit)
    assert result.exception.args == (2,)
    assert 'Error: No SUMMARY specified' in result.output


def test_todo_edit(runner, default_database, todo_factory):
    # This isn't a very thurough test, but at least catches obvious regressions
    # like startup crashes or typos.
    todo_factory()

    with patch('urwid.MainLoop'):
        result = runner.invoke(cli, ['edit', '1'])

    assert not result.exception
    assert 'YARR!' in result.output


@freeze_time('2017, 3, 20')
def test_list_today(tmpdir, runner, todo_factory):
    todo_factory(summary='started', start=datetime.datetime(2017, 3, 15))
    todo_factory(summary='nostart')
    todo_factory(summary='unstarted', start=datetime.datetime(2017, 3, 24))

    result = runner.invoke(cli, ['list', '--today'], catch_exceptions=False)

    assert not result.exception
    assert 'started' in result.output
    assert 'nostart' in result.output
    assert 'unstarted' not in result.output

    result = runner.invoke(cli, ['list'], catch_exceptions=False)

    assert not result.exception
    assert 'started' in result.output
    assert 'nostart' in result.output
    assert 'unstarted' in result.output

    path = tmpdir.join('config')
    path.write('today = yes\n', 'a')

    result = runner.invoke(cli, ['list'], catch_exceptions=False)

    assert not result.exception
    assert 'started' in result.output
    assert 'nostart' in result.output
    assert 'unstarted' not in result.output


def test_bad_start_date(runner):
    result = runner.invoke(cli, ['list', '--start'])
    assert result.exception
    assert (
        result.output.strip() == 'Error: --start option requires 2 arguments'
    )

    result = runner.invoke(cli, ['list', '--start', 'before'])
    assert result.exception
    assert (
        result.output.strip() == 'Error: --start option requires 2 arguments'
    )

    result = runner.invoke(cli, ['list', '--start', 'before', 'not_a_date'])
    assert result.exception
    assert (
        'Invalid value for "--start": Time description not recognized: '
        'not_a_date' in result.output
    )

    result = runner.invoke(cli, ['list', '--start', 'godzilla', '2017-03-22'])
    assert result.exception
    assert ("Format should be '[before|after] [DATE]'" in result.output)


def test_done(runner, todo_factory, default_database):
    todo = todo_factory()

    result = runner.invoke(cli, ['done', '1'])
    assert not result.exception

    default_database.update_cache()
    todo = next(default_database.todos(all=True))
    assert todo.percent_complete == 100
    assert todo.is_completed is True

    result = runner.invoke(cli, ['done', '17'])
    assert result.exception
    assert result.output.strip() == 'No todo with id 17.'


def test_id_printed_for_new(runner):
    result = runner.invoke(cli, [
        'new', '-l', 'default', 'show me an id'
    ])
    assert not result.exception
    assert result.output.strip().startswith('1')