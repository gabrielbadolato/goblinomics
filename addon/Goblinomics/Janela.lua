-- Janela do Goblinomics (GoblinomicsJanela): Resumo, Ofertas, Profissões e Coleta, com os dados do Dados.lua.
-- Abre pela moeda do minimapa. Fica num arquivo à parte: se algo aqui falhar, a dica do item continua.

local _, G = ...
if not G or not G.D then return end
local D = G.D
local dizer, moeda, numero = G.dizer, G.moeda, G.numero
local OURO, CINZA, VERDE, BRANCO = "|cffffd100", "|cff9d9d9d", "|cff40ff40", "|cffffffff"
local LINHAS, ALTURA = 15, 22
local TAXA = 0.05

local janela, abaAtual, linhasDaAba, deslocamento, selecionada = nil, "resumo", {}, 0, nil

-- ---- Dados ----

local function nome(id)
  return (D.nomes and D.nomes[id]) or ("item " .. id)
end

local function meuNome()
  local eu = UnitName and UnitName("player")
  return eu or ""
end

-- A lista "|Nome|Nome|" tem o personagem? O nome do jogo pode vir sem o sobrenome, então basta começar igual.
local function euSei(quem)
  local eu = meuNome()
  return quem ~= nil and eu ~= "" and string.find(quem, "|" .. eu, 1, true) ~= nil
end

local function iconeDe(id)
  local busca = (C_Item and C_Item.GetItemIconByID) or GetItemIcon
  if not busca then return nil end
  local ok, textura = pcall(busca, id)
  return ok and textura or nil
end

local function zonaAtual()
  local a = GetRealZoneText and GetRealZoneText() or ""
  local b = GetZoneText and GetZoneText() or ""
  return a, b
end

-- Receitas com lucro agora e com saída, da que mais rende por dia para a que menos.
local function receitas(soMinhas)
  local saida = {}
  for id, f in pairs(D.fab or {}) do
    local i = D.itens[id]
    if i and i.l and i.l > 0 and i.d and i.d >= 1 and (not soMinhas or euSei(f.q)) then
      saida[#saida + 1] = {id = id, f = f, i = i, porDia = i.l * i.d}
    end
  end
  table.sort(saida, function(a, b) return a.porDia > b.porDia end)
  return saida
end

-- Mapas para a profissão ("e" ervas, "m" minérios), do maior valor médio para o menor. O valor médio é o
-- dos materiais comuns com venda, sem a taxa do leilão, como na aba Coleta do site.
local function mapas(tipo)
  local saida = {}
  for _, z in ipairs(D.coleta or {}) do
    local ids = z[tipo]
    if ids then
      local soma, n, itens = 0, 0, {}
      for _, id in ipairs(ids) do
        local i = D.itens[id]
        if i and i.m then
          itens[#itens + 1] = {id = id, valor = i.m * (1 - TAXA)}
          if i.d and i.d > 0 then soma, n = soma + i.m * (1 - TAXA), n + 1 end
        end
      end
      table.sort(itens, function(a, b) return a.valor > b.valor end)
      if #itens > 0 then
        saida[#saida + 1] = {z = z.z, nv = z.nv, itens = itens, media = n > 0 and soma / n or 0}
      end
    end
  end
  table.sort(saida, function(a, b) return a.media > b.media end)
  return saida
end

-- ---- Auctionator: cria a lista de compras lá dentro ----

local function listaNoAuctionator(nomeDaLista, termos)
  local api = Auctionator and Auctionator.API and Auctionator.API.v1
  if not api or not api.CreateShoppingList then
    dizer("o Auctionator não está disponível para criar a lista.")
    return
  end
  if #termos == 0 then
    dizer("nada para pôr na lista.")
    return
  end
  local buscas = {}
  for _, t in ipairs(termos) do
    local busca
    if api.ConvertToSearchString then
      local ok, texto = pcall(api.ConvertToSearchString, G.QUEM_CHAMA, {searchString = t.nome, isExact = true, quantity = t.q})
      if ok and type(texto) == "string" then busca = texto end
    end
    -- Sem a conversão do Auctionator: o nome entre aspas é busca exata.
    buscas[#buscas + 1] = busca or ('"' .. t.nome .. '"')
  end
  local ok, erro = pcall(api.CreateShoppingList, G.QUEM_CHAMA, nomeDaLista, buscas)
  if ok then
    dizer(VERDE .. "lista criada no Auctionator:|r " .. nomeDaLista .. " (" .. #buscas .. " itens). Abra o leilão, aba Shopping.")
  else
    dizer("o Auctionator recusou a lista: " .. tostring(erro))
  end
end

-- ---- Conteúdo de cada aba: {texto do cabeçalho, linhas} ----
-- Linha: id (item), esq, meio, dir, titulo (linha de seção), dica (função que preenche a dica), dados.

local opcoes = {soMinhas = true, tipoDeColeta = "e"}

local function linhaDeReceita(r)
  return {id = r.id, esq = nome(r.id), meio = VERDE .. "+" .. moeda(r.i.l) .. "|r",
    dir = CINZA .. r.f.p .. " · ~" .. numero(r.i.d, true) .. "/dia|r", receita = r}
end

local function linhaDeOferta(id)
  local i = D.itens[id]
  if not i or not i.m or not i.h then return nil end
  local pct = math.floor((i.m - i.h) / i.h * 100 + 0.5)
  return {id = id, esq = nome(id), meio = moeda(i.m) .. VERDE .. " (" .. pct .. "%)|r",
    dir = CINZA .. "média " .. moeda(i.h) .. CINZA .. " · ~" .. numero(i.d or 0, true) .. "/dia|r"}
end

local function linhaDeMapa(m, posicao, aqui)
  local nomes = {}
  for k = 1, math.min(3, #m.itens) do nomes[#nomes + 1] = nome(m.itens[k].id) end
  local marca = aqui and (VERDE .. "> ") or (CINZA .. posicao .. ". |r")
  return {esq = marca .. (aqui and "" or BRANCO) .. m.z .. "|r" .. (m.nv ~= "" and (CINZA .. " " .. m.nv .. "|r") or ""),
    meio = moeda(m.media), dir = CINZA .. table.concat(nomes, ", ") .. (#m.itens > 3 and (" +" .. (#m.itens - 3)) or "") .. "|r",
    dica = function(dica)
      dica:AddLine(m.z)
      for _, item in ipairs(m.itens) do dica:AddDoubleLine(nome(item.id), moeda(item.valor), 1, 1, 1, 1, 1, 1) end
      dica:AddLine("Valor por unidade, sem a taxa do leilão.", 0.6, 0.6, 0.6, true)
    end}
end

local function mapasComAqui(tipo)
  local lista, a, b = mapas(tipo), zonaAtual()
  local linhas = {}
  for posicao, m in ipairs(lista) do
    local aqui = m.z == a or m.z == b
    local linha = linhaDeMapa(m, posicao, aqui)
    -- O mapa em que a pessoa está sobe para o topo.
    if aqui then table.insert(linhas, 1, linha) else linhas[#linhas + 1] = linha end
  end
  return linhas
end

local ABAS = {
  {chave = "resumo", rotulo = "Resumo", montar = function()
    local linhas = {}
    linhas[#linhas + 1] = {titulo = "Fabricar agora (receitas que este personagem sabe)"}
    local minhas = receitas(true)
    for k = 1, math.min(4, #minhas) do linhas[#linhas + 1] = linhaDeReceita(minhas[k]) end
    if #minhas == 0 then linhas[#linhas + 1] = {esq = CINZA .. "Nenhuma receita sua com lucro agora (ou o site ainda não leu este personagem).|r"} end
    linhas[#linhas + 1] = {titulo = "Pechinchas no leilão"}
    local n = 0
    for _, id in ipairs(D.ofertas or {}) do
      local linha = linhaDeOferta(id)
      if linha and n < 4 then linhas[#linhas + 1] = linha; n = n + 1 end
    end
    if n == 0 then linhas[#linhas + 1] = {esq = CINZA .. "Nenhuma pechincha agora.|r"} end
    linhas[#linhas + 1] = {titulo = "Coleta: melhores mapas de ervas"}
    local ervas = mapasComAqui("e")
    for k = 1, math.min(3, #ervas) do linhas[#linhas + 1] = ervas[k] end
    return "O que vale fazer agora. Passe o mouse numa linha para ver o item; as outras abas trazem as listas completas.", linhas
  end},
  {chave = "ofertas", rotulo = "Ofertas", montar = function()
    local linhas = {}
    for _, id in ipairs(D.ofertas or {}) do
      local linha = linhaDeOferta(id)
      if linha then linhas[#linhas + 1] = linha end
    end
    return "30% ou mais abaixo da média de 7 dias, vendendo 10 ou mais por dia. Anúncio não é venda: confira antes de comprar.", linhas
  end, colunas = {"Item", "Menor preço", "Média de 7 dias · vendas"}, acao = {rotulo = "Mandar tudo para o Auctionator", fazer = function(linhas)
    local termos = {}
    for _, l in ipairs(linhas) do if l.id then termos[#termos + 1] = {nome = nome(l.id)} end end
    listaNoAuctionator("Goblinomics: ofertas", termos)
  end}},
  {chave = "profissoes", rotulo = "Profissões", montar = function()
    local linhas = {}
    for _, r in ipairs(receitas(opcoes.soMinhas)) do linhas[#linhas + 1] = linhaDeReceita(r) end
    local quais = opcoes.soMinhas and ("só as que " .. (meuNome() ~= "" and meuNome() or "este personagem") .. " sabe") or "todas"
    return "Receitas com lucro agora, " .. quais .. ". Clique numa receita para escolhê-la; o lucro é por unidade.", linhas
  end, colunas = {"Receita", "Lucro por unidade", "Profissão · vendas"}, alternar = {rotulo = function() return opcoes.soMinhas and "Mostrar todas" or "Só as que eu sei" end,
    fazer = function() opcoes.soMinhas = not opcoes.soMinhas end},
  acao = {rotulo = "Materiais da escolhida para o Auctionator", fazer = function()
    if not selecionada or not selecionada.receita then
      dizer("clique primeiro numa receita da lista.")
      return
    end
    local r, termos, doNpc = selecionada.receita, {}, {}
    for k = 1, #r.f.m, 2 do
      local material, quantidade = r.f.m[k], r.f.m[k + 1]
      local noLeilao = D.itens[material] and D.itens[material].m
      local npc = D.npc and D.npc[material]
      -- O que o vendedor NPC tem mais barato não vai para a lista do leilão.
      if npc and (not noLeilao or npc <= noLeilao) then
        doNpc[#doNpc + 1] = quantidade .. " x " .. nome(material)
      else
        termos[#termos + 1] = {nome = nome(material), q = quantidade}
      end
    end
    listaNoAuctionator("Goblinomics: " .. nome(r.id), termos)
    if #doNpc > 0 then dizer("compre no vendedor NPC: " .. table.concat(doNpc, ", ") .. ".") end
  end}},
  {chave = "coleta", rotulo = "Coleta", montar = function()
    local a = zonaAtual()
    return "Mapas pelo valor médio do que nasce em cada um (QuestieDB). Você está em " .. (a ~= "" and a or "?")
      .. ". Passe o mouse para ver todos os materiais do mapa.", mapasComAqui(opcoes.tipoDeColeta)
  end, colunas = {"Mapa", "Valor médio (un.)", "O que mais vale lá"}, alternar = {rotulo = function() return opcoes.tipoDeColeta == "e" and "Ver minérios" or "Ver ervas" end,
    fazer = function() opcoes.tipoDeColeta = opcoes.tipoDeColeta == "e" and "m" or "e" end}},
  {chave = "opcoes", rotulo = "Opções", painel = true, montar = function()
    return "O que o addon mostra e avisa. As escolhas ficam guardadas para este personagem e para os outros.", {}
  end},
}

local function abaDe(chave)
  for _, a in ipairs(ABAS) do if a.chave == chave then return a end end
  return ABAS[1]
end

-- ---- Desenho ----
-- Duas aparências para a mesma janela. "jogo": a moldura, os botões e as abas padrão do próprio jogo.
-- "lisa": retângulos escuros com contorno dourado, no estilo do site; é também a reserva quando algum
-- modelo de moldura do jogo não existe neste cliente. A escolha fica em GoblinomicsOpcoes.pele.

local COR = {
  fundo = {0.04, 0.04, 0.05, 0.96}, faixa = {0.11, 0.095, 0.05, 1}, borda = {0.62, 0.50, 0.16, 1},
  linha = {1, 1, 1, 0.035}, realce = {1, 1, 1, 0.08}, escolhida = {1, 0.82, 0, 0.20},
  botao = {0.20, 0.16, 0.06, 1}, botaoAceso = {0.34, 0.27, 0.09, 1}, ouro = {1, 0.82, 0},
  apagado = {0.62, 0.62, 0.62}, trilho = {1, 1, 1, 0.06}, cursor = {0.62, 0.50, 0.16, 0.9},
}
local LARGURA = 720
-- Medidas que mudam com a aparência; preenchidas ao criar a janela.
local P = {}
local pele = "jogo"

local function retangulo(pai, camada, cor)
  local r = pai:CreateTexture(nil, camada)
  r:SetColorTexture(cor[1], cor[2], cor[3], cor[4] or 1)
  return r
end

-- Contorno de 1 pixel em volta do quadro.
local function contornar(quadro, cor)
  for _, lado in ipairs({{"TOPLEFT", "TOPRIGHT", true}, {"BOTTOMLEFT", "BOTTOMRIGHT", true},
                         {"TOPLEFT", "BOTTOMLEFT", false}, {"TOPRIGHT", "BOTTOMRIGHT", false}}) do
    local r = retangulo(quadro, "BORDER", cor)
    r:SetPoint(lado[1])
    r:SetPoint(lado[2])
    if lado[3] then r:SetHeight(1) else r:SetWidth(1) end
  end
end

local function texto(pai, fonte, cor)
  local t = pai:CreateFontString(nil, "OVERLAY", fonte or "GameFontHighlightSmall")
  if cor then t:SetTextColor(cor[1], cor[2], cor[3]) end
  t:SetJustifyH("LEFT")
  return t
end

-- Botão: o padrão do jogo na aparência "jogo"; liso com contorno dourado na outra.
local function botao(pai, rotulo, largura, aoClicar)
  local b
  if pele == "jogo" then
    b = CreateFrame("Button", nil, pai, "UIPanelButtonTemplate")
    b:SetSize(largura, 22)
    b:SetText(rotulo)
    b.SetRotulo = function(self, novo) self:SetText(novo) end
  else
    b = CreateFrame("Button", nil, pai)
    b:SetSize(largura, 24)
    b.fundo = retangulo(b, "BACKGROUND", COR.botao)
    b.fundo:SetAllPoints(b)
    contornar(b, COR.borda)
    b.rotulo = texto(b, "GameFontNormalSmall", COR.ouro)
    b.rotulo:SetPoint("CENTER")
    b.rotulo:SetText(rotulo)
    b.SetRotulo = function(self, novo) self.rotulo:SetText(novo) end
    b:SetScript("OnEnter", function(self) self.fundo:SetColorTexture(unpack(COR.botaoAceso)) end)
    b:SetScript("OnLeave", function(self) self.fundo:SetColorTexture(unpack(COR.botao)) end)
  end
  b:SetScript("OnClick", aoClicar)
  return b
end

local function desenharOpcoes()
  local o, op = janela.opcoes, GoblinomicsOpcoes
  o.dica:SetRotulo(op.dica == false and "Desligados" or "Ligados")
  o.aviso:SetRotulo(op.aviso and "Ligado" or "Desligado")
  o.vendedor:SetRotulo(op.vendedor == false and "Desligado" or "Ligado")
  o.pele:SetRotulo(op.pele == "lisa" and "Lisa" or "Do jogo")
end

local function desenhar()
  if not janela then return end
  local aba = abaDe(abaAtual)
  janela.marcarAbas()
  for k = 1, 3 do janela.colunas[k]:SetText(aba.colunas and aba.colunas[k] or "") end
  if aba.painel then
    for k = 1, LINHAS do janela.linhas[k]:Hide() end
    janela.trilho:Hide(); janela.cursor:Hide()
    janela.pagina:SetText("Goblinomics " .. G.VERSAO)
    janela.acao:Hide(); janela.alternar:Hide()
    janela.opcoes:Show()
    desenharOpcoes()
    return
  end
  janela.opcoes:Hide()
  local maximo = math.max(0, #linhasDaAba - LINHAS)
  if deslocamento > maximo then deslocamento = maximo end
  if deslocamento < 0 then deslocamento = 0 end
  for k = 1, LINHAS do
    local linha, dados = janela.linhas[k], linhasDaAba[k + deslocamento]
    linha.dados = dados
    if dados then
      local textura = dados.id and iconeDe(dados.id)
      if textura then linha.icone:SetTexture(textura); linha.icone:Show() else linha.icone:Hide() end
      -- Título de seção e linha só de texto ocupam a largura toda; as outras dividem com as colunas.
      local larga = dados.titulo or not (dados.meio or dados.dir)
      linha.esq:ClearAllPoints()
      linha.esq:SetPoint("LEFT", (dados.titulo or not dados.id) and 6 or 28, 0)
      linha.esq:SetWidth(larga and 660 or (dados.id and 280 or 302))
      linha.esq:SetText(dados.titulo and (OURO .. dados.titulo .. "|r") or (dados.esq or ""))
      linha.meio:SetText(dados.meio or "")
      linha.dir:SetText(dados.dir or "")
      if dados.titulo then
        linha.zebra:Hide(); linha.regua:Show()
      else
        linha.regua:Hide()
        if (k + deslocamento) % 2 == 0 then linha.zebra:Show() else linha.zebra:Hide() end
      end
      if dados == selecionada then linha.fundo:Show() else linha.fundo:Hide() end
      linha:Show()
    else
      linha:Hide()
    end
  end
  -- Barra de rolagem: só aparece quando há mais linhas do que cabem.
  if maximo > 0 then
    local trilho = LINHAS * ALTURA
    local tamanho = math.max(24, trilho * LINHAS / #linhasDaAba)
    janela.cursor:SetHeight(tamanho)
    janela.cursor:ClearAllPoints()
    janela.cursor:SetPoint("TOPRIGHT", janela, "TOPRIGHT", -P.margem + 6, P.topo - (trilho - tamanho) * deslocamento / maximo)
    janela.trilho:Show(); janela.cursor:Show()
    janela.pagina:SetText(string.format("%d-%d de %d", deslocamento + 1, math.min(deslocamento + LINHAS, #linhasDaAba), #linhasDaAba))
  else
    janela.trilho:Hide(); janela.cursor:Hide()
    janela.pagina:SetText("")
  end
  if aba.acao then janela.acao:SetRotulo(aba.acao.rotulo); janela.acao:Show() else janela.acao:Hide() end
  if aba.alternar then
    janela.alternar:SetRotulo(aba.alternar.rotulo())
    -- Sem o botão de ação ao lado, o de alternar ocupa o canto.
    janela.alternar:ClearAllPoints()
    if aba.acao then janela.alternar:SetPoint("LEFT", janela.acao, "RIGHT", 8, 0) else janela.alternar:SetPoint("BOTTOMLEFT", P.margem, P.rodape) end
    janela.alternar:Show()
  else
    janela.alternar:Hide()
  end
end

local function montar()
  local aba = abaDe(abaAtual)
  local ok, cabecalho, linhas = pcall(aba.montar)
  if not ok then
    dizer("a aba " .. aba.rotulo .. " falhou: " .. tostring(cabecalho))
    cabecalho, linhas = "Esta aba deu erro; a mensagem está no chat.", {}
  end
  linhasDaAba = linhas or {}
  janela.cabecalho:SetText(cabecalho or "")
  janela.estado:SetText(G.resumo())
  desenhar()
end

local function trocarAba(chave)
  abaAtual, deslocamento, selecionada = chave, 0, nil
  montar()
end

local function criarLinha(k)
  local linha = CreateFrame("Button", nil, janela)
  linha:SetSize(LARGURA - 2 * P.margem - 10, ALTURA)
  linha:SetPoint("TOPLEFT", P.margem, P.topo - (k - 1) * ALTURA)
  linha.zebra = retangulo(linha, "BACKGROUND", COR.linha)
  linha.zebra:SetAllPoints(linha)
  linha.fundo = retangulo(linha, "BORDER", COR.escolhida)
  linha.fundo:SetAllPoints(linha)
  linha.fundo:Hide()
  -- Risco dourado sob os títulos de seção.
  linha.regua = retangulo(linha, "BORDER", {COR.borda[1], COR.borda[2], COR.borda[3], 0.5})
  linha.regua:SetPoint("BOTTOMLEFT")
  linha.regua:SetPoint("BOTTOMRIGHT")
  linha.regua:SetHeight(1)
  linha.regua:Hide()
  local realce = retangulo(linha, "HIGHLIGHT", COR.realce)
  realce:SetAllPoints(linha)
  linha.icone = linha:CreateTexture(nil, "ARTWORK")
  linha.icone:SetSize(18, 18)
  linha.icone:SetPoint("LEFT", 4, 0)
  -- Sem a moldura cinza que vem nos ícones do jogo.
  linha.icone:SetTexCoord(0.07, 0.93, 0.07, 0.93)
  linha.esq = texto(linha, "GameFontHighlight")
  linha.esq:SetPoint("LEFT", 28, 0)
  linha.esq:SetWidth(280)
  linha.meio = texto(linha, "GameFontHighlight")
  linha.meio:SetPoint("LEFT", 312, 0)
  linha.meio:SetWidth(146)
  linha.meio:SetJustifyH("RIGHT")
  linha.dir = texto(linha, "GameFontHighlightSmall")
  linha.dir:SetPoint("LEFT", 474, 0)
  linha.dir:SetWidth(200)
  for _, t in ipairs({linha.esq, linha.meio, linha.dir}) do
    if t.SetWordWrap then t:SetWordWrap(false) end
  end
  linha:SetScript("OnEnter", function(self)
    local dados = self.dados
    if not dados or (not dados.id and not dados.dica) then return end
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    if dados.dica then
      dados.dica(GameTooltip)
    else
      -- A dica do próprio item, que já traz as linhas do Goblinomics.
      local ok = pcall(GameTooltip.SetHyperlink, GameTooltip, "item:" .. dados.id)
      if not ok then GameTooltip:AddLine(nome(dados.id)) end
    end
    GameTooltip:Show()
  end)
  linha:SetScript("OnLeave", function() GameTooltip:Hide() end)
  linha:SetScript("OnClick", function(self)
    if self.dados and self.dados.id then
      selecionada = self.dados
      desenhar()
    end
  end)
  return linha
end

-- A aba Opções: o que antes era um painel à parte.
local function criarOpcoes()
  local o = CreateFrame("Frame", nil, janela)
  o:SetPoint("TOPLEFT", P.margem + 4, P.topo + 12)
  o:SetSize(LARGURA - 2 * P.margem - 8, LINHAS * ALTURA + 12)
  local function opcao(k, rotuloDoBotao, titulo, explicacao, aoClicar)
    local b = botao(o, rotuloDoBotao, 110, function() aoClicar(); desenharOpcoes() end)
    b:SetPoint("TOPLEFT", 0, -(k - 1) * 36)
    local t = texto(o, "GameFontHighlight")
    t:SetPoint("LEFT", b, "RIGHT", 12, 6)
    t:SetText(titulo)
    local e = texto(o, "GameFontHighlightSmall", COR.apagado)
    e:SetPoint("LEFT", b, "RIGHT", 12, -7)
    e:SetText(explicacao)
    return b
  end
  o.dica = opcao(1, "", "Dados na dica do item", "As linhas do Goblinomics ao passar o mouse num item.",
    function() GoblinomicsOpcoes.dica = GoblinomicsOpcoes.dica == false end)
  o.aviso = opcao(2, "", "Aviso de preços velhos", "O botão no alto da tela quando os preços carregados passam de 1h15.",
    function() if G.alternarAviso then G.alternarAviso() end end)
  o.vendedor = opcao(3, "", "Aviso no vendedor", "Ao abrir um vendedor NPC, lista no chat o que ele vende que rende no leilão.",
    function() GoblinomicsOpcoes.vendedor = GoblinomicsOpcoes.vendedor == false end)
  o.pele = opcao(4, "", "Aparência da janela", "Do jogo: moldura e botões padrão. Lisa: escura e dourada, como o site. Vale ao recarregar.",
    function() GoblinomicsOpcoes.pele = GoblinomicsOpcoes.pele == "lisa" and "jogo" or "lisa" end)
  opcao(5, "Diagnóstico", "O que este cliente do jogo oferece", "Para mandar ao Claude quando algo não funcionar.", function()
    if o.textoDiag:IsShown() then
      o.textoDiag:Hide()
    else
      o.textoDiag:SetText(G.diagnostico and G.diagnostico() or "indisponível")
      o.textoDiag:Show()
    end
  end)
  o.textoDiag = texto(o, "GameFontHighlightSmall")
  o.textoDiag:SetPoint("TOPLEFT", 0, -5 * 36 - 2)
  o.textoDiag:SetWidth(LARGURA - 2 * P.margem - 8)
  if o.textoDiag.SetWordWrap then o.textoDiag:SetWordWrap(true) end
  o.textoDiag:Hide()
  o:Hide()
  return o
end

-- O que as duas aparências têm em comum: comportamento da janela, textos, linhas, opções e rodapé.
local function criarConteudo()
  janela:SetFrameStrata("HIGH")
  janela:EnableMouse(true)
  janela:SetMovable(true)
  janela:RegisterForDrag("LeftButton")
  janela:SetScript("OnDragStart", janela.StartMoving)
  janela:SetScript("OnDragStop", janela.StopMovingOrSizing)
  janela:SetClampedToScreen(true)
  _G["GoblinomicsJanela"] = janela
  if UISpecialFrames then table.insert(UISpecialFrames, "GoblinomicsJanela") end
  janela:EnableMouseWheel(true)
  janela:SetScript("OnMouseWheel", function(_, sentido)
    deslocamento = deslocamento - sentido * 3
    desenhar()
  end)

  janela.cabecalho = texto(janela, "GameFontHighlightSmall", COR.apagado)
  janela.cabecalho:SetPoint("TOPLEFT", P.margem + 4, P.topo + 50)
  janela.cabecalho:SetWidth(LARGURA - 2 * P.margem - 8)
  janela.cabecalho:SetHeight(26)
  janela.cabecalho:SetJustifyV("TOP")
  -- Títulos das colunas, alinhados com as das linhas.
  janela.colunas = {}
  for k, c in ipairs({{28, 280, "LEFT"}, {312, 146, "RIGHT"}, {474, 200, "LEFT"}}) do
    local t = texto(janela, "GameFontNormalSmall", COR.ouro)
    t:SetPoint("TOPLEFT", P.margem + c[1], P.topo + 17)
    t:SetWidth(c[2])
    t:SetJustifyH(c[3])
    janela.colunas[k] = t
  end
  janela.linhas = {}
  for k = 1, LINHAS do janela.linhas[k] = criarLinha(k) end
  janela.trilho = retangulo(janela, "BORDER", COR.trilho)
  janela.trilho:SetPoint("TOPRIGHT", -P.margem + 6, P.topo)
  janela.trilho:SetSize(4, LINHAS * ALTURA)
  janela.cursor = retangulo(janela, "ARTWORK", COR.cursor)
  janela.cursor:SetWidth(4)
  janela.opcoes = criarOpcoes()

  janela.pagina = texto(janela, "GameFontHighlightSmall", COR.apagado)
  janela.pagina:SetPoint("BOTTOMRIGHT", -P.margem - 4, P.rodape + 6)
  janela.acao = botao(janela, "", 290, function()
    local aba = abaDe(abaAtual)
    if aba.acao then
      local ok, erro = pcall(aba.acao.fazer, linhasDaAba)
      if not ok then dizer("não deu certo: " .. tostring(erro)) end
    end
  end)
  janela.acao:SetPoint("BOTTOMLEFT", P.margem, P.rodape)
  janela.alternar = botao(janela, "", 150, function()
    local aba = abaDe(abaAtual)
    if aba.alternar then
      aba.alternar.fazer()
      deslocamento, selecionada = 0, nil
      montar()
    end
  end)
  janela.alternar:SetPoint("LEFT", janela.acao, "RIGHT", 8, 0)
  janela:Hide()
end

-- ---- Aparência "jogo": moldura, botões e abas padrão do cliente ----

local function criarNoEstiloDoJogo()
  pele = "jogo"
  local modelo
  for _, tentativa in ipairs({"ButtonFrameTemplate", "BasicFrameTemplateWithInset", "BasicFrameTemplate"}) do
    local ok, quadro = pcall(CreateFrame, "Frame", "GoblinomicsJanela", UIParent, tentativa)
    if ok and quadro then janela, modelo = quadro, tentativa; break end
  end
  if not janela then error("nenhum modelo de moldura do jogo existe neste cliente") end
  local comRetrato = modelo == "ButtonFrameTemplate"
  -- Com a barra de botões do modelo, o quadro interno termina 26 pixels acima do fundo: é onde ficam os nossos.
  P = {margem = 10, topo = comRetrato and -112 or -104, rodape = 4}
  janela:SetSize(LARGURA, -P.topo + LINHAS * ALTURA + 34)
  janela:SetPoint("CENTER", UIParent, "CENTER", 0, 30)

  -- Título e, quando o modelo tem o círculo do retrato, a moeda dentro dele.
  local titulo = "Goblinomics"
  if janela.SetTitle then
    pcall(janela.SetTitle, janela, titulo)
  else
    local t = janela.TitleText or (janela.TitleContainer and janela.TitleContainer.TitleText)
    if t and t.SetText then t:SetText(titulo) end
  end
  if comRetrato then
    local posto = janela.SetPortraitToAsset and pcall(janela.SetPortraitToAsset, janela, G.ICONE)
    if not posto then
      local retrato = (janela.PortraitContainer and janela.PortraitContainer.portrait) or janela.portrait or janela.Portrait
      if retrato and retrato.SetTexture then retrato:SetTexture(G.ICONE) end
    end
  end

  janela.estado = texto(janela, "GameFontHighlightSmall")
  janela.estado:SetPoint("TOPLEFT", comRetrato and 66 or 14, -36)
  local atualizar = botao(janela, "Atualizar preços", 130, function() G.recarregar() end)
  atualizar:SetPoint("TOPRIGHT", -10, -30)

  -- Abas penduradas embaixo da janela, como nas janelas do próprio jogo.
  local abas, anterior = {}, nil
  for k, aba in ipairs(ABAS) do
    local b
    for _, tentativa in ipairs({"PanelTabButtonTemplate", "CharacterFrameTabButtonTemplate"}) do
      local ok, feito = pcall(CreateFrame, "Button", "GoblinomicsJanelaTab" .. k, janela, tentativa)
      if ok and feito then b = feito; break end
    end
    if not b then error("nenhum modelo de aba do jogo existe neste cliente") end
    b:SetID(k)
    b:SetText(aba.rotulo)
    if PanelTemplates_TabResize then pcall(PanelTemplates_TabResize, b, 0) end
    if anterior then
      -- As abas novas encostam uma na outra; as antigas se sobrepõem um pouco.
      b:SetPoint("LEFT", anterior, "RIGHT", b.LeftActive and 1 or -15, 0)
    else
      b:SetPoint("TOPLEFT", janela, "BOTTOMLEFT", 11, 2)
    end
    b:SetScript("OnClick", function() trocarAba(aba.chave) end)
    b.chave = aba.chave
    abas[k], anterior = b, b
  end
  janela.Tabs, janela.numTabs = abas, #abas
  if PanelTemplates_SetNumTabs then pcall(PanelTemplates_SetNumTabs, janela, #abas) end
  janela.marcarAbas = function()
    for k, b in ipairs(abas) do
      if b.chave == abaAtual and PanelTemplates_SetTab then pcall(PanelTemplates_SetTab, janela, k) end
    end
  end
  criarConteudo()
end

-- ---- Aparência "lisa": escura e dourada, como o site ----

local function criarLisa()
  pele = "lisa"
  P = {margem = 14, topo = -132, rodape = 11}
  janela = CreateFrame("Frame", nil, UIParent)
  janela:SetSize(LARGURA, -P.topo + LINHAS * ALTURA + 60)
  janela:SetPoint("CENTER", UIParent, "CENTER", 0, 30)
  retangulo(janela, "BACKGROUND", COR.fundo):SetAllPoints(janela)
  contornar(janela, COR.borda)

  -- Faixa do título: ícone, nome, estado dos dados, atualizar e fechar.
  local faixa = retangulo(janela, "BORDER", COR.faixa)
  faixa:SetPoint("TOPLEFT", 1, -1)
  faixa:SetPoint("TOPRIGHT", -1, -1)
  faixa:SetHeight(42)
  local icone = janela:CreateTexture(nil, "ARTWORK")
  icone:SetSize(28, 28)
  icone:SetPoint("TOPLEFT", P.margem, -8)
  icone:SetTexture(G.ICONE)
  local titulo = texto(janela, "GameFontNormalLarge", COR.ouro)
  titulo:SetPoint("LEFT", icone, "RIGHT", 8, 0)
  titulo:SetText("Goblinomics")
  janela.estado = texto(janela, "GameFontHighlightSmall", COR.apagado)
  janela.estado:SetPoint("LEFT", titulo, "RIGHT", 14, -1)
  local fechar = botao(janela, "X", 24, function() janela:Hide() end)
  fechar:SetPoint("TOPRIGHT", -P.margem, -10)
  local atualizar = botao(janela, "Atualizar preços", 118, function() G.recarregar() end)
  atualizar:SetPoint("RIGHT", fechar, "LEFT", -8, 0)

  -- Abas: texto, com um traço dourado sob a que está aberta.
  local sobAbas = retangulo(janela, "BORDER", {COR.borda[1], COR.borda[2], COR.borda[3], 0.45})
  sobAbas:SetPoint("TOPLEFT", 1, -72)
  sobAbas:SetPoint("TOPRIGHT", -1, -72)
  sobAbas:SetHeight(1)
  local abas = {}
  for k, aba in ipairs(ABAS) do
    local b = CreateFrame("Button", nil, janela)
    b:SetSize(104, 28)
    b:SetPoint("TOPLEFT", P.margem + (k - 1) * 106, -44)
    b.fundo = retangulo(b, "BACKGROUND", {1, 0.82, 0, 0.07})
    b.fundo:SetAllPoints(b)
    b.sublinhado = retangulo(b, "ARTWORK", COR.ouro)
    b.sublinhado:SetPoint("BOTTOMLEFT")
    b.sublinhado:SetPoint("BOTTOMRIGHT")
    b.sublinhado:SetHeight(2)
    local realce = retangulo(b, "HIGHLIGHT", COR.realce)
    realce:SetAllPoints(b)
    b.rotulo = texto(b, "GameFontNormal")
    b.rotulo:SetPoint("CENTER")
    b.rotulo:SetText(aba.rotulo)
    b.chave = aba.chave
    b:SetScript("OnClick", function() trocarAba(aba.chave) end)
    abas[k] = b
  end
  janela.marcarAbas = function()
    for _, b in ipairs(abas) do
      local ativa = b.chave == abaAtual
      b.rotulo:SetTextColor(unpack(ativa and COR.ouro or COR.apagado))
      if ativa then b.sublinhado:Show(); b.fundo:Show() else b.sublinhado:Hide(); b.fundo:Hide() end
    end
  end
  local rodape = retangulo(janela, "BORDER", COR.faixa)
  rodape:SetPoint("BOTTOMLEFT", 1, 1)
  rodape:SetPoint("BOTTOMRIGHT", -1, 1)
  rodape:SetHeight(44)
  criarConteudo()
end

local function criar()
  if GoblinomicsOpcoes.pele ~= "lisa" then
    local ok, erro = pcall(criarNoEstiloDoJogo)
    if ok then return end
    -- Algum modelo do jogo faltou ou se comportou diferente: esconde o que ficou pela metade e usa a lisa.
    dizer("a aparência do jogo falhou (" .. tostring(erro) .. "); usando a lisa.")
    if janela then janela:Hide() end
    janela = nil
  end
  criarLisa()
end

-- Abre ou fecha a janela; com uma aba pedida, abre nela.
function G.alternarJanela(aba)
  if not janela then criar() end
  if janela:IsShown() and not aba then
    janela:Hide()
  else
    if aba then abaAtual, deslocamento, selecionada = aba, 0, nil end
    montar()
    janela:Show()
  end
end

-- ---- No vendedor: o que ele vende que rende no leilão ----

local function precoNoVendedor(k)
  -- A interface nova devolve uma tabela; a antiga, vários valores.
  if C_MerchantFrame and C_MerchantFrame.GetItemInfo then
    local info = C_MerchantFrame.GetItemInfo(k)
    if info then return info.price, info.stackCount or 1, info.numAvailable end
  end
  if GetMerchantItemInfo then
    local _, _, preco, lote, disponiveis = GetMerchantItemInfo(k)
    return preco, lote or 1, disponiveis
  end
  return nil
end

local function olharVendedor()
  if not GetMerchantNumItems or not GetMerchantItemLink then return end
  local achados = {}
  for k = 1, GetMerchantNumItems() do
    local link = GetMerchantItemLink(k)
    local id = link and tonumber(string.match(link, "item:(%d+)"))
    local i = id and D.itens[id]
    local preco, lote, disponiveis = precoNoVendedor(k)
    if i and i.m and preco and preco > 0 then
      local custo = preco / (lote or 1)
      local lucro = i.m * (1 - TAXA) - custo
      -- Só o que tem saída e sobra de pelo menos 20% sobre o que se paga aqui.
      if i.d and i.d >= 1 and lucro > custo * 0.2 then
        achados[#achados + 1] = {link = link, custo = custo, venda = i.m, lucro = lucro, d = i.d, limitado = disponiveis and disponiveis > 0}
      end
    end
  end
  if #achados == 0 then return end
  table.sort(achados, function(a, b) return a.lucro > b.lucro end)
  dizer("este vendedor tem " .. #achados .. (#achados == 1 and " item que rende" or " itens que rendem") .. " no leilão:")
  for k = 1, math.min(5, #achados) do
    local a = achados[k]
    dizer("  " .. a.link .. " custa " .. moeda(a.custo) .. ", vende a " .. moeda(a.venda) .. " (~" .. numero(a.d, true) .. "/dia)"
      .. (a.limitado and (OURO .. " · estoque limitado|r") or ""))
  end
end

local quadro = CreateFrame("Frame")
quadro:RegisterEvent("MERCHANT_SHOW")
quadro:SetScript("OnEvent", function()
  if GoblinomicsOpcoes and GoblinomicsOpcoes.vendedor == false then return end
  local ok, erro = pcall(olharVendedor)
  if not ok then dizer("a leitura do vendedor falhou: " .. tostring(erro)) end
end)
