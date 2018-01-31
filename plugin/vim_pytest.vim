let g:vp_max_split_size = 30

hi pytestSuccess ctermfg=40
hi pytestWarning ctermfg=220
hi pytestError ctermfg=196

hi pytestPassed ctermfg=black ctermbg=154
hi pytestFailed ctermfg=white ctermbg=160
hi pytestSkipped ctermfg=black ctermbg=220
hi pytestWaiting ctermfg=white ctermbg=67
hi pytestStage ctermfg=white ctermbg=63

sign define pytest_outcome_passed text=P texthl=pytestPassed
sign define pytest_outcome_failed text=F texthl=pytestFailed
sign define pytest_outcome_error text=E texthl=pytestFailed
sign define pytest_outcome_xpassed text=XP texthl=pytestPassed
sign define pytest_outcome_xfailed text=XF texthl=pytestFailed
sign define pytest_outcome_skipped text=S texthl=pytestSkipped

sign define pytest_collected text=.. texthl=pytestWaiting
sign define pytest_stage_setup text=S> texthl=pytestStage
sign define pytest_stage_call text=C> texthl=pytestStage
sign define pytest_stage_teardown text=T> texthl=pytestStage

nmap <silent><leader>p :VP file<CR>
nmap <silent><leader>f :VP function<CR>
nmap <silent><leader>C :VP stop<CR>
nmap <silent><F10> :VP toggle<CR>


function! VPEcho(msg, hl)
    let l:msg = []
    if type(a:msg) != type([])
        let l:msg = split(a:msg, "\n")
    else
        let l:msg = a:msg
    endif
    let l:msg = map(l:msg, 'substitute(v:val, "\t", "        ", "")')

    exe 'echohl ' . a:hl
    for line in l:msg
        echom '[VP] ' . line
    endfor
    echohl None
endfunction

function! VPCreateSplit(num_lines)
    let l:split_id = bufnr('Results.pytest')
    if l:split_id == -1
        let l:size = min([a:num_lines, g:vp_max_split_size, winheight("%") / 2])
        exe 'botright ' . l:size . ' new Results.pytest'
        wincmd p
    else
        let l:size = min([a:num_lines, g:vp_max_split_size, (winheight("%") + winheight('Results.pytest')) / 2 + 1])
        exe l:split_id 'resize ' . l:size
    endif
endfunction

function! VPDeleteSplit()
    let l:split_id = bufnr('Results.pytest')
    if l:split_id > -1
        exe 'bdelete ' . l:split_id
    endif
endfunction

function! s:VPSetupWindow()
    if winnr("$") == 1
        q
    endif

    setlocal buftype=nowrite
    setlocal bufhidden=wipe
    setlocal nobuflisted
    setlocal noswapfile
    setlocal nowrap
    setlocal filetype=pytest
    setlocal winfixheight
endfunction

autocmd! BufEnter Results.pytest call s:VPSetupWindow()
