@echo off

pushd "%~dp0"

FOR /R %1% %%F IN (.) DO (
    ls
)

popd
