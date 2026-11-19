import pytest

from paw.domain.files import InputError, inspect_csv, validate_name


@pytest.mark.parametrize(
    "data,code",
    [
        (b"", "invalid_headers"),
        (b"a,b\n", "empty_csv"),
        (b"a,a\n1,2\n", "invalid_headers"),
        (b"a, a \n1,2\n", "invalid_headers"),
        (b"a,\n1,2\n", "invalid_headers"),
        (b"a,b\n1\n", "inconsistent_columns"),
        (b"a\n\n", "inconsistent_columns"),
        (b'a\n"unfinished', "invalid_csv"),
        (b"a\n\xff", "invalid_encoding"),
        (b"a\n\x00", "invalid_csv"),
        (b"x" * (10 * 1024 * 1024 + 1), "file_too_large"),
        (b"a\n" + b"x\n" * 100001, "too_many_rows"),
        ((",".join("c" + str(i) for i in range(201)) + "\n").encode(), "too_many_columns"),
        (b"a\n" + b"x" * 32769, "cell_too_large"),
    ],
)
def test_invalid_csv_has_safe_codes(data, code):
    with pytest.raises(InputError) as error:
        inspect_csv(data)
    assert error.value.code == code


def test_unicode_bom_quotes_and_formula_are_data():
    data = '\ufeffword,explanation\r\n"tere, maailm","привіт\nсвіт"\r\n=1+1,literal\r\n'.encode()
    result = inspect_csv(data)
    assert result.row_count == 2
    assert result.column_count == 2
    assert result.size_bytes == len(data)


def test_explicit_semicolon():
    assert inspect_csv(b"a;b\n1;2\n", ";").column_count == 2
    with pytest.raises(InputError, match="invalid_delimiter"):
        inspect_csv(b"a\n1\n", "\t")


@pytest.mark.parametrize(
    "name",
    [
        "../private.csv",
        "/tmp/file.csv",
        "C:\\file.csv",
        "folder/file.csv",
        "bad\x00.csv",
        "name.txt",
        "",
        "x" * 256 + ".csv",
    ],
)
def test_names_cannot_supply_paths(name):
    with pytest.raises(InputError, match="invalid_filename"):
        validate_name(name)


def test_limit_boundaries():
    assert inspect_csv(b"a\n" + b"x\n" * 100000).row_count == 100000
    assert inspect_csv(b"a\n" + b"x" * 32768).row_count == 1
    assert validate_name("Навчання.CSV") == "Навчання.CSV"
