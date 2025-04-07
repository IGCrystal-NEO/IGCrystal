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
        let buffer = ''; // 用于暂存不完整的数据片段

        const processStream = ({ done, value }) => {
          if (done) {
            console.log('SSE stream closed');
            setTimeout(() => {
              this.eventSource = null;
              this.createEventSource();
            }, 2000);
            return;
          }

          // 将新的数据追加到缓存中，并尽可能解码完整数据
          buffer += decoder.decode(value, { stream: true });
          // 按行分割数据
          const lines = buffer.split('\n');
          // 最后一行可能是不完整的，保留在 buffer 中
          buffer = lines.pop();

          lines.forEach(line => {
            if (line.startsWith('data:')) {
              const data = line.substring(5).trim();
              try {
                let data_json = JSON.parse(data);
                if (data_json.type === 'log') {
                  this.log_cache.push(data_json);
                  if (this.log_cache.length > this.log_cache_max_len) {
                    this.log_cache.shift();
                  }
                }
              } catch (err) {
                console.error('JSON parse error for data:', data, err);
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

      // 保存 controller 以便以后能关闭连接
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
