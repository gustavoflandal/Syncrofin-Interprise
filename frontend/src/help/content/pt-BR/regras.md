# Regras

**Regras** automatizam o trabalho repetitivo: quando uma transação chega (importada, sincronizada ou digitada) e
bate com as **condições**, a regra executa **ações** (categorizar, renomear, marcar…).

A tela tem abas: **Regras** (as de categorização, descritas aqui), **Esperando você** e **Histórico**. As duas
últimas pertencem à [conciliação](help:conciliacao) de cobranças.

## Como uma regra funciona

Uma regra tem:

- **Nome** e **Prioridade** (um número: a regra de número **menor** é avaliada **primeiro**);
- **Condições**: o que precisa ser verdade;
- **Ações**: o que fazer quando é.

### Condições

Cada condição compara um **campo** com um valor:

| Campo | Exemplo |
|-------|---------|
| **Descrição** | descrição *contém* "UBER" |
| **Pessoa importada** | o nome bruto que veio do banco |
| **Notas** | as notas da transação |
| **Valor** | valor *é igual a* / maior / menor |
| **Tipo** | **Despesa (debit)** ou **Receita (credit)** |
| **Conta** | a conta da transação |
| **Pessoa** | a pessoa vinculada |
| **Data** | a data da transação |

E o **operador**: *contém*, *não contém*, *é igual a*, *é diferente de*, *começa com*, *termina com*, *regex*
(expressão regular, para casos avançados), *é*, *não é*.

Combine várias condições com **E (AND)** ou **OU (OR)**. **Adicionar grupo** permite aninhar: um grupo junta suas
próprias condições com E ou OU. Toda condição precisa de valor (uma condição em branco corresponderia a *todas* as
transações, e o sistema não deixa salvar).

### Ações

| Ação | O que faz |
|------|-----------|
| **Definir categoria** | Atribui a categoria. |
| **Definir descrição** | Troca a descrição por uma normalizada (até 500 caracteres). A original fica guardada. |
| **Atribuir pessoa** | Vincula uma [pessoa](help:pessoas). |
| **Adicionar tags/notas** | Acrescenta notas ou `#tags`. |
| **Ignorar transação** | Marca como ignorada (não conta nos totais). |

## Criar uma regra

1. **Adicionar** → dê um nome, monte as condições e as ações.
2. **Pré-visualizar** mostra **quais transações já existentes casariam** e o que mudaria (*"N transações correspondem; M seriam alteradas"*).
3. Marque **Aplicar ações correspondentes às transações existentes** se quiser que a regra atue também no passado, e
   **Também substituir categorias existentes** se puder sobrescrever categorias já definidas.
4. Salve. A regra fica **ativa**: use **Ativar/Desativar** para ligar e desligar sem excluir.

Atalho: em [Transações](help:transacoes), o menu de uma transação oferece **Criar Regra**, já com a descrição
preenchida.

## Buscar, filtrar e ordenar

Busque por nome e filtre por **categoria**, **status** (ativas/inativas) e **ação**. Ordene por **Prioridade**,
**Nome** ou **Categoria**.

## Pacotes de regras

Os **Pacotes de Regras** são conjuntos prontos (por exemplo, para bancos e comerciantes comuns).
**Instalar** adiciona as regras do pacote. Se o pacote depende de categorias padrão que você não tem, marque
**Criar também as categorias padrão que o pacote precisa**.

## Exportar e importar

**Exportar** baixa suas regras em JSON; **Importar** carrega um arquivo. Atenção: importar **substitui** as regras de
categorização atuais, e isso **não pode ser desfeito**: o sistema pede confirmação.

## Redefinir e reaplicar

**Redefinir e reaplicar** limpa categorias, notas e descrições **gerenciadas por regras** nas transações
correspondentes e aplica as regras de novo. Use com cuidado.

## Boas práticas

- Comece por regras **específicas** (ex.: descrição contém "NETFLIX") antes das genéricas.
- Use a **pré-visualização** antes de salvar.
- Prefira **contém** a **é igual a**: bancos costumam acrescentar códigos e datas ao texto.
