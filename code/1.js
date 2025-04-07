import { defineStore } from 'pinia';
import axios from 'axios';

export const useCommonStore = defineStore({
  id: 'common',
  state: () => ({
    eventSource: null,
    log_cache: [],
    sse_connected: false,

    log_cache_max_len: 1000,
    startTime: -1,

    tutorial_map: {
      "qq_official_webhook": "https://astrbot.app/deploy/platform/qqofficial/webhook.html",
      "qq_official": "https://astrbot.app/deploy/platform/qqofficial/websockets.html",
      "aiocqhttp": "https://astrbot.app/deploy/platform/aiocqhttp/napcat.html",
      "wecom": "https://astrbot.app/deploy/platform/wecom.html",
      "gewechat": "https://astrbot.app/deploy/platform/gewechat.html",
      "lark": "https://astrbot.app/deploy/platform/lark.html",
      "telegram": "https://astrbot.app/deploy/platform/telegram.html",
      "dingtalk": "https://astrbot.app/deploy/platform/dingtalk.html",
    },

    pluginMarketData: [],
  }),
  actions: {
    createEventSource() {
      if (this.eventSource) {
        return;
      }
      const controller = new AbortController();
      const { signal } = controller;
      const headers = {
        'Content-Type': 'multipart/form-data',
        'Authorization': 'Bearer ' + localStorage.getItem('token')
      };
      fetch('/api/live-log', {
        method: 'GET',
        headers,
        signal,
        cache: 'no-cache',
      }).then(response => {
        if (!response.ok) {
          throw new Error(`SSE connection failed: ${response.status}`);
        }
        console.log('SSE stream opened');
        this.sse_connected = true;

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = ''; // 用于暂存不完整的消息片段
        const MAX_BUFFER_LENGTH = 10000; // 设置缓冲区最大长度

        const processStream = ({ done, value }) => {
          if (done) {
            console.log('SSE stream closed');
            setTimeout(() => {
              this.eventSource = null;
              this.createEventSource();
            }, 2000);
            return;
          }

          // 追加数据到缓冲区，确保流式解码
          buffer += decoder.decode(value, { stream: true });

          // 检查缓冲区长度，防止无限积累
          if (buffer.length > MAX_BUFFER_LENGTH) {
            console.warn('Buffer length exceeded, truncating old data');
            buffer = buffer.substring(buffer.length - MAX_BUFFER_LENGTH);
          }

          // 使用双换行符分割消息块
          const parts = buffer.split('\n\n');
          // 最后一部分可能是不完整的，保留到下一次处理
          buffer = parts.pop();

          parts.forEach(part => {
            // 提取所有以 "data:" 开头的行，并拼接成一个完整的字符串
            const lines = part.split('\n').filter(line => line.startsWith('data:'));
            const dataStr = lines.map(line => line.substring(5).trim()).join('');
            // 检查是否看起来完整（假设 JSON 对象以 } 结尾）
            if (!dataStr.trim().endsWith('}')) {
              // 数据可能还未完整接收，将其重新放回缓冲区后跳过解析
              buffer = dataStr + "\n\n" + buffer;
              return;
            }
            let data_json = {};
            try {
              data_json = JSON.parse(dataStr);
            } catch (e) {
              console.error('Invalid JSON:', dataStr, e);
              // 构造默认日志信息，以保证后续流程不受影响
              data_json = {
                type: 'log',
                data: dataStr,
                level: 'INFO',
                time: new Date().toISOString(),
              };
            }
            if (data_json.type === 'log') {
              this.log_cache.push(data_json);
              if (this.log_cache.length > this.log_cache_max_len) {
                this.log_cache.shift();
              }
            }
          });
          return reader.read().then(processStream);
        };

        reader.read().then(processStream);
      }).catch(error => {
        console.error('SSE error:', error);
        this.log_cache.push('SSE Connection failed, retrying in 5 seconds...');
        setTimeout(() => {
          this.eventSource = null;
          this.createEventSource();
        }, 1000);
      });

      // 保存 controller 以便以后关闭连接
      this.eventSource = controller;
    },
    closeEventSourcet() {
      if (this.eventSource) {
        this.eventSource.abort();
        this.eventSource = null;
      }
    },
    getLogCache() {
      return this.log_cache;
    },
    getStartTime() {
      if (this.startTime !== -1) {
        return this.startTime;
      }
      axios.get('/api/stat/start-time').then((res) => {
        this.startTime = res.data.data.start_time;
      });
    },
    getTutorialLink(platform) {
      return this.tutorial_map[platform];
    },
    async getPluginCollections(force = false) {
      if (!force && this.pluginMarketData.length > 0) {
        return Promise.resolve(this.pluginMarketData);
      }
      return axios.get('/api/plugin/market_list')
        .then((res) => {
          let data = [];
          for (let key in res.data.data) {
            data.push({
              "name": key,
              "desc": res.data.data[key].desc,
              "author": res.data.data[key].author,
              "repo": res.data.data[key].repo,
              "installed": false,
              "version": res.data.data[key]?.version ? res.data.data[key].version : "未知",
              "social_link": res.data.data[key]?.social_link,
              "tags": res.data.data[key]?.tags ? res.data.data[key].tags : [],
              "logo": res.data.data[key]?.logo ? res.data.data[key].logo : "",
              "pinned": res.data.data[key]?.pinned ? res.data.data[key].pinned : false,
            });
          }
          this.pluginMarketData = data;
          return data;
        })
        .catch((err) => {
          this.toast("获取插件市场数据失败: " + err, "error");
          return Promise.reject(err);
        });
    },
  }
});
